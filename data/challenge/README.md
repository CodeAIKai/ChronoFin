# ChronoFin real-company challenge v1

This directory contains a deliberately small, fully offline evaluator
challenge curated by an AI agent from official public disclosures. Its
historical name is “post-freeze,” but the available evidence supports a more
limited statement: the repository retains a historical v1 result chain, not
an externally timestamped proof that every first-run evaluator byte was frozen
before the cases were visible.

The immutable data unit is exactly `challenge_v1.json` plus the three files in
`source_excerpts/`. `FROZEN.sha256` records their four SHA-256 digests, and
these data files remained unchanged across both repair chains.

Scope:

- three real companies and three official disclosure representations;
- one pre-publication refusal and one post-publication answer per company;
- one deterministic future-leak negative per company;
- AI-curated deterministic gold, not human-expert annotation, fresh Hy3
  generation, a hidden set, or a statistical held-out benchmark.

There are two separately scoped result chains:

- **historical v1 repository record:** 3/6 → 6/6, with historical results and
  final-result evaluator hashes retained in independent ledgers. There is no
  external trusted timestamp, the complete evaluator identity of the first
  failed run is not verifiable, and the current source tree differs from v1;
- **current v2 seen-data regression:** 0/6 → 6/6 plus 3/3 future-leak
  negatives rejected. The current evaluator, adapter, predecessor/final
  results, and repair manifest are independently hashed. Because the cases
  were already known during current hardening, this is regression evidence,
  not post-freeze or held-out validation.

The ledgers and manifest are:

- `FROZEN.sha256` — four immutable data files;
- `HISTORICAL_V1_RESULTS.sha256` and `EVALUATOR_FROZEN.sha256` — retained v1
  record;
- `EVALUATOR_CURRENT_V2.sha256` and `ADAPTER_CURRENT_V2.sha256` — current
  evaluator/adapter identities;
- `CURRENT_V2_REGRESSION_CHAIN.sha256` and `CURRENT_V2_ADAPTER_FIX.json` —
  current predecessor, final result, and scoped repair.

Run offline from the repository root:

```bash
PYTHONPATH=src python scripts/run_postfreeze_challenge.py --verify-only
PYTHONPATH=src python scripts/run_postfreeze_challenge.py
python scripts/verify_submission.py --compact
```

The submission verifier independently recomputes available file hashes,
cross-checks embedded manifests and both failure→repair sequences, and enforces
the seen-regression/no-held-out declarations. See
`docs/postfreeze_challenge_report.md` for provenance, results, and limitations.
