# Stage 7 evaluation artifacts

The four files in this directory are the accepted deterministic fixture
baseline for 105 held-out scenarios repeated under empty, relevant, and
misleading advisory-memory conditions. The `live/` directory contains the
accepted, separately opted-in Amazon Bedrock campaign. Both campaigns pass
315/315 runs and all 105 scenarios at 3/3 consistency; the live campaign also
passes 720/720 structured reasoning calls without fallback.

These files are evaluator outputs and must never be loaded into the agent's
prompt, working state, tools, or long-term memory.

- `run_results.jsonl`: 315 typed run records.
- `metrics_summary.json`: aggregate gates and cohort metrics.
- `scenario_summary.csv`: 105 scenario-level consistency rows.
- `failures.jsonl`: only failed run records; empty for an accepted campaign.

Latency is machine- and service-dependent. Live cost is an estimate from the
token counts and the explicit rates supplied to the runner.
