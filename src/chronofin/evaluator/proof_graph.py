"""Typed proof graph used for lineage checks and causal mutation oracles."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from ..models import AnalysisAnswer, ClaimType


class NodeKind(str, Enum):
    SOURCE = "source"
    CALCULATION = "calculation"
    CLAIM = "claim"
    RUBRIC = "rubric"


class EdgeKind(str, Enum):
    SUPPORTS = "supports"
    OPERAND_OF = "operand_of"
    DERIVES = "derives"
    CONTRADICTS = "contradicts"
    REQUIRES = "requires"


@dataclass(frozen=True)
class ProofNode:
    id: str
    kind: NodeKind
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProofEdge:
    source: str
    target: str
    kind: EdgeKind


@dataclass(frozen=True)
class ProofGraphIssue:
    code: str
    message: str
    severity: str = "error"
    node_id: str = ""


class ProofGraph:
    """A deliberately small DAG, with no hidden model-generated edges."""

    def __init__(self, nodes: Iterable[ProofNode], edges: Iterable[ProofEdge]) -> None:
        self.nodes = {node.id: node for node in nodes}
        self.edges = list(edges)
        self._outgoing: dict[str, list[ProofEdge]] = defaultdict(list)
        self._incoming: dict[str, list[ProofEdge]] = defaultdict(list)
        for edge in self.edges:
            self._outgoing[edge.source].append(edge)
            self._incoming[edge.target].append(edge)

    @classmethod
    def from_answer(cls, answer: AnalysisAnswer) -> "ProofGraph":
        nodes: list[ProofNode] = []
        edges: list[ProofEdge] = []
        for evidence in answer.evidence:
            nodes.append(
                ProofNode(
                    id=evidence.id,
                    kind=NodeKind.SOURCE,
                    payload={
                        "chunk_id": evidence.chunk_id,
                        "document_id": evidence.document_id,
                        "page": evidence.page,
                        "published_at": evidence.published_at,
                    },
                )
            )
        for calculation in answer.calculations:
            nodes.append(
                ProofNode(
                    id=calculation.id,
                    kind=NodeKind.CALCULATION,
                    payload={"expression": calculation.expression, "result": calculation.result, "unit": calculation.unit},
                )
            )
            for operand in calculation.operands:
                for evidence_id in operand.evidence_ids:
                    edges.append(ProofEdge(evidence_id, calculation.id, EdgeKind.OPERAND_OF))
                for upstream_id in operand.calculation_ids:
                    edges.append(ProofEdge(upstream_id, calculation.id, EdgeKind.DERIVES))
        for claim in answer.claims:
            nodes.append(
                ProofNode(
                    id=claim.id,
                    kind=NodeKind.CLAIM,
                    payload={
                        "claim_type": claim.claim_type.value,
                        "semantic_key": claim.semantic_key,
                        "entity": claim.entity,
                        "period": claim.period,
                        "unit": claim.unit,
                    },
                )
            )
            for evidence_id in claim.evidence_ids:
                edges.append(ProofEdge(evidence_id, claim.id, EdgeKind.SUPPORTS))
            if claim.calculation_id:
                edges.append(ProofEdge(claim.calculation_id, claim.id, EdgeKind.DERIVES))
        return cls(nodes, edges)

    def validate(self) -> list[ProofGraphIssue]:
        issues: list[ProofGraphIssue] = []
        for edge in self.edges:
            if edge.source not in self.nodes:
                issues.append(ProofGraphIssue("missing_source_node", f"edge source {edge.source} does not exist", node_id=edge.source))
            if edge.target not in self.nodes:
                issues.append(ProofGraphIssue("missing_target_node", f"edge target {edge.target} does not exist", node_id=edge.target))
        for node in self.nodes.values():
            incoming = self._incoming.get(node.id, [])
            if node.kind == NodeKind.CALCULATION and not any(edge.kind == EdgeKind.OPERAND_OF for edge in incoming):
                issues.append(ProofGraphIssue("calculation_without_source", f"calculation {node.id} has no evidence-bound operand", node_id=node.id))
            if node.kind == NodeKind.CLAIM:
                claim_type = node.payload.get("claim_type")
                if claim_type in {ClaimType.FACT.value, ClaimType.DERIVED.value} and not incoming:
                    issues.append(ProofGraphIssue("unsupported_claim", f"{claim_type} claim {node.id} has no proof edge", node_id=node.id))
                if claim_type == ClaimType.DERIVED.value and not any(edge.kind == EdgeKind.DERIVES for edge in incoming):
                    issues.append(ProofGraphIssue("derived_without_calculation", f"derived claim {node.id} has no calculation edge", node_id=node.id))
        if self._has_cycle():
            issues.append(ProofGraphIssue("cycle", "proof graph must be acyclic"))
        return issues

    def _has_cycle(self) -> bool:
        indegree = {node_id: 0 for node_id in self.nodes}
        for edge in self.edges:
            if edge.source in self.nodes and edge.target in self.nodes:
                indegree[edge.target] += 1
        queue = deque(node_id for node_id, degree in indegree.items() if degree == 0)
        visited = 0
        while queue:
            node_id = queue.popleft()
            visited += 1
            for edge in self._outgoing.get(node_id, []):
                if edge.target not in indegree:
                    continue
                indegree[edge.target] -= 1
                if indegree[edge.target] == 0:
                    queue.append(edge.target)
        return visited != len(self.nodes)

    def descendants(self, source_ids: Iterable[str], kinds: set[NodeKind] | None = None) -> set[str]:
        queue = deque(source_ids)
        visited = set(source_ids)
        result: set[str] = set()
        while queue:
            current = queue.popleft()
            for edge in self._outgoing.get(current, []):
                if edge.target in visited:
                    continue
                visited.add(edge.target)
                queue.append(edge.target)
                node = self.nodes.get(edge.target)
                if node and (kinds is None or node.kind in kinds):
                    result.add(edge.target)
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [
                {"id": node.id, "kind": node.kind.value, "payload": node.payload}
                for node in self.nodes.values()
            ],
            "edges": [
                {"source": edge.source, "target": edge.target, "kind": edge.kind.value}
                for edge in self.edges
            ],
        }
