# Stage 7 — Evaluation and Robustness

## 1. Status and purpose

Stage 7 implements the frozen held-out evaluation campaign described in
[`05_evaluation_plan.md`](../pre-development-design/05_evaluation_plan.md). It measures the complete
Stage 5/6 workflow with deterministic evaluator-owned oracles rather than
asking the same model to grade itself.

Both acceptance lanes are complete. The reproducible fixture campaign and the
qualifying Amazon Bedrock campaign each pass all 315 runs, with all 105
held-out scenarios passing under all three memory conditions. The qualifying
live campaign completed 720/720 validated structured reasoning calls with no
fallbacks and a 100% schema-validation pass rate.

## 2. Frozen campaign

The evaluator selects only the Stage 3 `evaluation` split:

```text
7 scenario families
× 15 held-out scenarios per family
= 105 held-out scenarios

105 scenarios
× 3 isolated repetitions
= 315 end-to-end runs
```

The three repetitions deliberately cover the required memory conditions:

| Repetition | Memory condition | Expected property |
| --- | --- | --- |
| 1 | Empty | Correctness without historical advice |
| 2 | Relevant | Advice may help, but current tools remain authoritative |
| 3 | Misleading | Incorrect advice cannot override current tools or safety gates |

Every repetition receives a fresh Stage 4 runtime, Stage 5 control plane,
checkpointer, decision provider, and in-memory advisory store. No transaction,
checkpoint, model audit, or memory write can influence a later repetition.

## 3. Deterministic oracle

`Stage7EvaluationCampaign` keeps the execution contracts and scenario ground
truth on the evaluator side. The graph receives only the same observable
intake and tools used in Stage 5.

Each run checks:

- expected versus actual final outcome;
- every required and forbidden transition;
- exact pre- and post-action verifier sequences;
- direct registration or committed-receipt completion predicates;
- approval request/intermediate semantics and approval/admin separation;
- clarification impact and small/material resume routing;
- persisted interrupt and resume behavior without write replay;
- expected replan and retry counters plus hard-cap exhaustion;
- verified-`DONE` memory-update gating;
- duplicate/replayed transaction receipts;
- evaluator-only key leakage into persisted graph state;
- observable tool-call and action-result success;
- reasoning success/fallback counts, token usage, latency, and optional cost;
  and
- result signatures across the three memory conditions as a trace-variability
  diagnostic, without requiring incidental model routing choices to be byte-for-byte
  identical when every deterministic oracle still passes.

An unexpected exception becomes a normalized `RUNNER_EXCEPTION` result. The
campaign continues so failures remain visible in `failures.jsonl`.

## 4. Acceptance gates

The canonical report is accepted only when:

```text
run count                         = 315
held-out scenario count           = 105
repetitions per scenario          = 3
valid runs                        = 315
scenarios passing 3/3             = 105
memory/tool/approval violations   = 0
```

A Bedrock campaign additionally requires:

```text
structured-call success rate >= 95%
```

Model or credential failure may fall back safely to deterministic decisions,
so task correctness can remain intact. The additional live threshold prevents
that resilience behavior from being mislabeled as successful model coverage.

## 5. Report artifacts

The reproducible fixture baseline is stored in [`../evaluation/`](../evaluation/):

```text
evaluation/
├── run_results.jsonl
├── metrics_summary.json
├── scenario_summary.csv
├── failures.jsonl
└── live/
    ├── run_results.jsonl
    ├── metrics_summary.json
    ├── scenario_summary.csv
    └── failures.jsonl
```

`run_results.jsonl` contains one typed record per run. `scenario_summary.csv`
contains one row per held-out scenario. `failures.jsonl` is empty only when no
run violates an oracle. The live folder is overwritten only by an explicitly
opted-in Bedrock campaign.

## 6. Accepted fixture baseline

The accepted local baseline produced:

| Metric | Result |
| --- | ---: |
| Runs passed | 315 / 315 |
| Scenarios passing 3/3 | 105 / 105 |
| Task completion rate | 100% |
| Valid resolution rate | 100% |
| Dynamic-failure recovery | 100% |
| Correct escalation | 100% |
| Approval compliance | 100% |
| Clarification routing | 100% |
| Checkpoint/resume integrity | 100% |
| Memory override violations | 0 |
| Memory write-gate violations | 0 |
| Post-action false completions | 0 |
| Average observable tool calls | 18.057 |
| Average graph steps | 14.210 |

The tool-call success rate is lower than 100% by design because expected
dynamic failures, unavailable paths, and pending outcomes are valid normalized
tool results. Correct recovery and escalation are evaluated separately.

## 7. Accepted Bedrock campaign

The live campaign is independently protected by:

```text
RUN_BEDROCK_EVALUATION=1
```

This is separate from the two-request Stage 6 live-test opt-in. The runner
uses the configured model and writes token/cost data only when current pricing
is supplied explicitly.

The qualifying live campaign produced:

| Metric | Result |
| --- | ---: |
| Runs passed | 315 / 315 |
| Scenarios passing 3/3 | 105 / 105 |
| Structured reasoning calls | 720 / 720 |
| Schema-validation pass rate | 100% |
| Safe reasoning fallbacks | 0 |
| Input tokens | 751,959 |
| Output tokens | 31,604 |
| Total tokens | 783,563 |
| Estimated cost | $0.03074369 |
| Average end-to-end latency | 1,589.794 ms |
| Exact cross-memory result signatures | 75 / 105 |

All required and forbidden transition oracles passed for every run. The 30
non-identical signature groups reflect conservative live-model variation in
specialist selection or replanning metadata, not different validity or final
outcomes; all 105 scenarios still passed 3/3 and misleading memory caused no
override violations.

An earlier non-qualifying run also completed all 315 cases correctly after its
temporary token expired, because the deterministic fallback remained safe. It
was correctly rejected by the live gate: only 377 of 720 reasoning calls
returned validated structured output (52.3611%). This failure led to the
explicit 95% live schema threshold and confirms that fallback resilience is
reported separately from successful model coverage.

The cost estimate uses the explicit invocation rates supplied to the runner;
it does not embed pricing in application code. The rates used for the accepted run were
the published Nova Micro standard rates on 1 September 2026: $0.035 per million
input tokens and $0.14 per million output tokens. See the official
[Amazon Bedrock pricing page](https://aws.amazon.com/bedrock/pricing/).

## 8. Commands

Run the accepted reproducible baseline:

```powershell
.venv\Scripts\python.exe scripts\run_stage7_evaluation.py `
  --mode fixture `
  --output-dir evaluation
```

Run the qualifying live lane only with intentionally supplied credentials:

```powershell
$env:RUN_BEDROCK_EVALUATION='1'
.venv\Scripts\python.exe scripts\run_stage7_evaluation.py `
  --mode bedrock `
  --output-dir evaluation\live `
  --input-usd-per-million 0.035 `
  --output-usd-per-million 0.14
```

The command exits non-zero when deterministic runs fail, scenario consistency
falls below 3/3, or a Bedrock campaign misses the 95% schema threshold.

## 9. Stage 8 handoff

Stage 8 may build the demonstration UI and operational packaging over these
reports. It must not move evaluator data into agent context, weaken the
acceptance thresholds, reuse mutable state across runs, or replace
deterministic correctness with an LLM judge.
