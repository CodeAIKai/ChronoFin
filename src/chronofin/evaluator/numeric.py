"""Safe expression execution and numeric-lineage checks."""

from __future__ import annotations

import ast
import math
import operator
import re
from dataclasses import dataclass
from typing import Mapping

from ..models import Calculation, Claim, ClaimType, Evidence


ALLOWED_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
ALLOWED_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
NUMBER = re.compile(r"(?<![\d.])-?\d[\d,]*(?:\.\d+)?")
NON_VALUE_IDENTIFIER = re.compile(
    r"(?i)\b(?:CALC|CLAIM|EVIDENCE|EVID|EV)[-_]?\d+\b"
)
LABELLED_PERIOD = re.compile(
    r"(?i)\b(?:FY(?:19|20)\d{2}|(?:19|20)\d{2}Q[1-4]|Q[1-4](?:FY)?(?:19|20)\d{2})\b"
)


class UnsafeExpression(ValueError):
    pass


def safe_evaluate(expression: str, variables: Mapping[str, float]) -> float:
    if len(expression) > 500:
        raise UnsafeExpression("expression is too long")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise UnsafeExpression(f"invalid expression: {exc}") from exc

    def evaluate(node: ast.AST, depth: int = 0) -> float:
        if depth > 30:
            raise UnsafeExpression("expression is too deep")
        if isinstance(node, ast.Expression):
            return evaluate(node.body, depth + 1)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise UnsafeExpression(f"unknown operand: {node.id}")
            return float(variables[node.id])
        if isinstance(node, ast.BinOp) and type(node.op) in ALLOWED_BINARY:
            left = evaluate(node.left, depth + 1)
            right = evaluate(node.right, depth + 1)
            if isinstance(node.op, ast.Pow) and abs(right) > 12:
                raise UnsafeExpression("power exponent is outside the safe range")
            return float(ALLOWED_BINARY[type(node.op)](left, right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in ALLOWED_UNARY:
            return float(ALLOWED_UNARY[type(node.op)](evaluate(node.operand, depth + 1)))
        raise UnsafeExpression(f"disallowed syntax: {type(node).__name__}")

    result = evaluate(tree)
    if not math.isfinite(result):
        raise UnsafeExpression("result is not finite")
    return result


def expression_names(expression: str) -> set[str]:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return set()
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


def numeric_tokens(text: str) -> set[str]:
    values: set[str] = set()
    for raw in NUMBER.findall(text):
        normalized = raw.replace(",", "")
        try:
            value = float(normalized)
        except ValueError:
            continue
        values.add(f"{value:.12g}")
    return values


def value_appears(value: float, text: str, tolerance: float = 1e-9) -> bool:
    for token in numeric_tokens(text):
        if math.isclose(float(token), value, rel_tol=tolerance, abs_tol=tolerance):
            return True
    return False


def rounded_value_appears(value: float, text: str) -> bool:
    """Match a displayed derived value using its explicit decimal precision."""

    # Formula/evidence identifiers and labelled reporting periods are metadata,
    # not candidate calculation results.  Without this projection, ``CALC1``
    # can spuriously validate an expected value such as 1.5 because the old
    # integer-rounding tolerance treated its suffix ``1`` as a displayed value.
    visible_text = NON_VALUE_IDENTIFIER.sub(" ", text)
    visible_text = LABELLED_PERIOD.sub(" ", visible_text)
    for raw in NUMBER.findall(visible_text):
        normalized = raw.replace(",", "")
        try:
            observed = float(normalized)
        except ValueError:
            continue
        decimals = len(normalized.rsplit(".", 1)[1]) if "." in normalized else 0
        rounding_tolerance = 0.5 * (10 ** -decimals)
        if math.isclose(observed, value, rel_tol=1e-9, abs_tol=max(1e-9, rounding_tolerance)):
            return True
    return False


@dataclass(frozen=True)
class NumericAudit:
    execution_accuracy: float
    leaf_binding_accuracy: float
    trace_coverage: float
    unit_consistency: float
    claim_value_accuracy: float
    claim_text_accuracy: float
    issues: tuple[str, ...]


def audit_calculations(
    calculations: list[Calculation],
    evidence: Mapping[str, Evidence],
    evidence_text: Mapping[str, str],
    claims: list[Claim] | None = None,
    tolerance: float = 1e-6,
) -> NumericAudit:
    claims = claims or []
    execution_ok = 0
    bound_leaves = 0
    valid_leaf_values = 0
    referenced_leaves = 0
    unit_ok = 0
    issues: list[str] = []
    calculation_index = {item.id: item for item in calculations}
    for calculation in calculations:
        variables = {operand.name: operand.value for operand in calculation.operands}
        names = expression_names(calculation.expression)
        declared = set(variables)
        if names != declared:
            missing = sorted(names - declared)
            unused = sorted(declared - names)
            issues.append(f"{calculation.id}: operand mismatch missing={missing}, unused={unused}")
        try:
            actual = safe_evaluate(calculation.expression, variables)
            if math.isclose(actual, calculation.result, rel_tol=tolerance, abs_tol=tolerance):
                execution_ok += 1
            else:
                issues.append(f"{calculation.id}: declared result {calculation.result} != executed {actual}")
        except (UnsafeExpression, ZeroDivisionError, OverflowError) as exc:
            issues.append(f"{calculation.id}: execution failed: {exc}")
        for operand in calculation.operands:
            referenced_leaves += 1
            valid_ids = [item for item in operand.evidence_ids if item in evidence]
            valid_calculations = [
                item for item in operand.calculation_ids
                if item in calculation_index and item != calculation.id
                and math.isclose(calculation_index[item].result, operand.value, rel_tol=tolerance, abs_tol=tolerance)
            ]
            if valid_ids or valid_calculations:
                bound_leaves += 1
            if valid_calculations or any(value_appears(operand.value, evidence_text.get(item, "")) for item in valid_ids):
                valid_leaf_values += 1
            else:
                issues.append(f"{calculation.id}.{operand.name}: value not found in bound evidence")
            explicit_scale = "1000" in calculation.expression and ("million" in calculation.unit.lower() or "百万" in calculation.unit)
            if not operand.unit or not calculation.unit or operand.unit == calculation.unit or calculation.unit in {"%", "百分点", "倍"} or explicit_scale:
                unit_ok += 1
            else:
                # Different operand/result units can be valid for ratios. It is
                # flagged but not made a hard failure when an explicit unit exists.
                unit_ok += 0.5
    total_calculations = len(calculations)
    leaf_denominator = max(1, referenced_leaves)
    numeric_claims = [claim for claim in claims if claim.value is not None]
    valid_claim_values = 0
    valid_claim_texts = 0
    for claim in numeric_claims:
        if claim.claim_type == ClaimType.DERIVED and claim.calculation_id in calculation_index:
            valid = math.isclose(
                float(claim.value), calculation_index[claim.calculation_id].result,
                rel_tol=tolerance, abs_tol=tolerance,
            )
        else:
            valid = any(value_appears(float(claim.value), evidence_text.get(item, "")) for item in claim.evidence_ids)
        if valid:
            valid_claim_values += 1
        else:
            issues.append(f"{claim.id}: typed claim value is not bound to evidence or calculation")
        text_matches = (
            rounded_value_appears(float(claim.value), claim.text)
            if claim.claim_type == ClaimType.DERIVED
            else value_appears(float(claim.value), claim.text)
        )
        if text_matches:
            valid_claim_texts += 1
        else:
            issues.append(f"{claim.id}: natural-language claim does not contain its typed numeric value")
    return NumericAudit(
        execution_accuracy=execution_ok / total_calculations if calculations else 1.0,
        leaf_binding_accuracy=valid_leaf_values / leaf_denominator if calculations else 1.0,
        trace_coverage=bound_leaves / leaf_denominator if calculations else 1.0,
        unit_consistency=unit_ok / leaf_denominator if calculations else 1.0,
        claim_value_accuracy=valid_claim_values / len(numeric_claims) if numeric_claims else 1.0,
        claim_text_accuracy=valid_claim_texts / len(numeric_claims) if numeric_claims else 1.0,
        issues=tuple(issues),
    )
