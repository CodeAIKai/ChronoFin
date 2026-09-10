# Real-company challenge: historical record and current regression

> 适用版本：历史规则评估器及其确定性回归。当前开放式研究应用见[实验分析报告](最终实验分析报告.md)与[十维评估方法](开放式评估方法.md)。下文的“当前”指该历史阶段。

## Result in one sentence

The four challenge-data files are unchanged. The repository-local historical
v1 record preserves a 3/6 → 6/6 repair chain, while the current hardened
evaluator preserves a separate **seen-data regression** of 0/6 → 6/6 and
rejects all 3/3 future-leak negatives at 20/100. Neither chain is human
evaluation, a hidden test set, or a statistical held-out estimate.

## The evidence boundary

“Post-freeze” is the historical name of this challenge, not a claim that the
current source tree was frozen before the cases were visible. The strongest
defensible statements are:

- `challenge_v1.json` and the three local source excerpts match the same four
  SHA-256 entries in `data/challenge/FROZEN.sha256`;
- the two retained historical result files match their independent result
  ledger, and the historical final result embeds evaluator hashes matching the
  retained v1 evaluator ledger;
- there is **no external trusted timestamp**, the complete evaluator identity
  of the first failed historical run cannot be verified, and the historical
  runner source is not available under its recorded hash;
- the current evaluator differs from the v1 evaluator in multiple modules, so
  a current rerun cannot be presented as the original frozen evaluation;
- because the cases were visible during current hardening, current-v2 results
  are regression evidence only.

This is deliberately narrower than saying “the evaluator was frozen before
the challenge.” The repository can authenticate its retained bytes and their
internal references; it cannot supply an independent chronology that was not
externally timestamped at the time.

## Why this set exists

The synthetic mutation benchmark stress-tests known failure types but does not
exercise unfamiliar issuer representations. This small set adds an offline
conformance/regression check over three official disclosure formats without
pretending that three technology companies establish broad generalization.

The immutable data unit contains exactly four files:

1. `data/challenge/challenge_v1.json`;
2. `data/challenge/source_excerpts/apple_sec_xbrl_fy2024.md`;
3. `data/challenge/source_excerpts/microsoft_ir_html_fy2025.md`;
4. `data/challenge/source_excerpts/nvidia_cfo_pdf_fy2025.md`.

Their hashes are in `data/challenge/FROZEN.sha256`. The dataset JSON SHA-256
is:

```text
9f7a57883c4f9a38ffba33f7a5aa86faef7eeabdb0c20d05a6c9537597be373e
```

## Official-source coverage

| Company | Official representation | Published | Point-in-time pair | Exact short source spans |
|---|---|---:|---|---|
| Apple Inc. | [SEC EDGAR XBRL presentation HTML](https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/R3.htm) ([filing index](https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/0000320193-24-000123-index.htm)) | 2024-11-01 | 2024-10-30 refuse; 2024-11-02 answer | `Net sales … 391,035`; `Net income … 93,736` |
| Microsoft Corporation | [issuer IR HTML with XBRL concepts](https://www.microsoft.com/en-us/Investor/earnings/fy-2025-Q4/income-statements) ([dated release](https://www.microsoft.com/en-us/investor/earnings/fy-2025-q4/press-release-webcast)) | 2025-07-30 | 2025-07-29 refuse; 2025-07-31 answer | `Total revenue … 281,724`; `Net income … 101,832` |
| NVIDIA Corporation | [issuer CFO commentary PDF](https://investor.nvidia.com/files/doc_financials/2025/Q425/Q4FY25-CFO-Commentary.pdf) ([dated newsroom release](https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-fourth-quarter-and-fiscal-2025)) | 2025-02-26 | 2025-02-25 refuse; 2025-02-27 answer | `Revenue $130,497`; `Net income $72,880` |

The local files are AI-transcribed short excerpts rather than redistributed
full reports. Their hashes authenticate the local transcription, not the
continued availability or byte identity of the upstream websites.

## Declarative gold

Each post-publication case specifies two source-bound facts and one
deterministic net-income-margin calculation:

| Company / period | Revenue or net sales (USD million) | GAAP net income (USD million) | Derived margin |
|---|---:|---:|---:|
| Apple FY2024 | 391,035 | 93,736 | 23.971255769943866% |
| Microsoft FY2025 | 281,724 | 101,832 | 36.146015248967075% |
| NVIDIA FY2025 | 130,497 | 72,880 | 55.848027157712444% |

Each pre-publication case is `unanswerable`. Its deterministic materializer
creates a canonical low-confidence `UNKNOWN` claim, uses no future evidence,
and records the later target disclosure in the exclusion log. Each negative
reuses a post-publication answer under the pre-publication cutoff, violating
both the answerability oracle and the time boundary.

These are deterministic gold materializations, not fresh Hy3 generations.

## Two separately scoped result chains

| Scope | Initial | Final | Future-leak negatives | Interpretation |
|---|---:|---:|---:|---|
| Historical v1 repository record | 3/6 | 6/6 | 3/3 rejected | retained evidence of an adapter/schema repair; chronology is not externally attested |
| Current v2 seen-data regression | 0/6 | 6/6 | 3/3 rejected at 20 | regression after evaluator hardening; not post-freeze or held-out evidence |

### Historical v1 record

The historical first run left pre-publication refusals as empty claim lists
and omitted the evaluator's expected-answerability argument. The retained
repair added typed `UNKNOWN` nodes and passed the already-declared oracle; the
four challenge-data files did not change. The preserved artifacts are:

- `results/postfreeze_challenge_v1.json` — 3/6 initial result;
- `results/postfreeze_challenge_v1_after_adapter_fix.json` — 6/6 repaired
  result;
- `data/challenge/HISTORICAL_V1_RESULTS.sha256` — hashes of both results;
- `data/challenge/EVALUATOR_FROZEN.sha256` — evaluator hashes embedded by the
  historical final result.

The result SHA-256 digests are respectively
`dd0337fd20b5d34e2b946f005b3b1ab54fec85c053000f54d3174d9c6f959302`
and
`c384b34410ca2d66ee6ecd97d3b5b54031d369e89736af635d1809d6b6dbfa05`.

This chain does **not** establish the complete evaluator identity of the first
3/6 run and has no external trusted timestamp. It must therefore be described
as a repository-local historical record, not a cryptographic proof of when the
challenge was created relative to all executed code.

### Current v2 seen-data regression

Red-team hardening changed the evaluator and visible-projection protocol. The
current code is independently pinned by
`data/challenge/EVALUATOR_CURRENT_V2.sha256`; the materialization runner is
pinned separately by `data/challenge/ADAPTER_CURRENT_V2.sha256`.

The first current-v2 regression scored 0/6 valid cases (mean 55) while still
rejecting 3/3 future leaks. It exposed a general metric-slot alias gap for
underscored `net_income`/`net_income_margin` semantic keys. Extending the
general alias registry and its unit test produced 6/6 valid cases at mean 100
and again rejected 3/3 negatives at mean 20. No challenge question, source,
date, value, quote, or gold label changed.

The current artifacts are:

- `results/postfreeze_challenge_v1_current_regression.json` — 0/6 predecessor;
- `results/postfreeze_challenge_v1_current_regression_after_slot_fix.json` —
  6/6 final regression;
- `data/challenge/CURRENT_V2_ADAPTER_FIX.json` — scoped repair manifest;
- `data/challenge/CURRENT_V2_REGRESSION_CHAIN.sha256` — hashes of the two
  results and repair manifest.

## Independent integrity checks

The data, historical results, historical evaluator manifest, current
evaluator, current adapter, and current repair chain have separate ledgers.
`scripts/verify_submission.py` independently parses those ledgers, recomputes
the hashes of every presently verifiable file, compares embedded manifests,
checks both failure→repair sequences and enforces the declarations
`seen_regression_fixture`, `postfreeze_relative_to_current_evaluator=false`,
and `heldout_claimed=false`. It does not treat a self-reported `verified=true`
field as sufficient evidence. The clean-room workflow also regenerates the
current regression as an executable step.

## Reproduction

No API key, model call, network access, or optional dependency is required:

```bash
PYTHONPATH=src python scripts/run_postfreeze_challenge.py --verify-only
PYTHONPATH=src python scripts/run_postfreeze_challenge.py
python scripts/verify_submission.py --compact
```

The first command checks the immutable data, historical record, current
evaluator, current adapter, and current predecessor. The second independently
materializes and scores the current seen-data regression.

## Limitations

- Curation and transcription were done by an AI agent; no finance expert
  adjudicated the questions or gold.
- Three large technology issuers and nine cases are too small and
  sector-biased for a population or generalization estimate.
- Valid answers are deterministic materializations of declarative gold, not
  fresh Hy3 outputs; this measures evaluator/adapter conformance.
- Only exact cited spans are stored offline, not complete copyrighted reports;
  upstream pages may later change or disappear.
- Without a semantic judge, factual credit is restricted to exact evidence
  spans for FACT claims and canonical executed-calculation projections for
  DERIVED claims. Lexical overlap is reported only as a diagnostic and earns
  no factual credit.
