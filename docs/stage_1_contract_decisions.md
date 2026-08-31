# Stage 1 Contract Decisions

This note records structural interpretations needed to make the Stage 1 data
contracts unambiguous. It does not introduce NTU academic rules.

## Scenario ground truth

The scenario contract uses `valid_initial_paths`, `valid_final_paths`, and
`invalid_paths`. This distinguishes a route that is valid before a dynamic
event from the different route that may remain valid after replanning.

Ground truth is grouped under `ScenarioGroundTruth`. The future agent receives
only `Scenario.to_agent_context()`, which excludes ground truth and future event
injections.

## Cross-programme cases

`Student.programme` remains the primary programme and
`Student.additional_programmes` represents second-major or double-degree rule
associations required by Scenario Family 5. Programme codes use a validated open
string type rather than an exhaustive four-value enum because the stated product
scope is all included CCDS programmes and the current official list still needs
verification.

## Transactions

`TransactionResult` represents one ordered attempt. `TransactionScript` contains
one or more results so a deterministic scenario can describe failure followed by
recovery without flattening the sequence.

## Offering data

`CourseOffering` represents the immutable sourced semester snapshot. The
separate generated `OfferingState` represents simulator-controlled runtime
availability. Unknown sourced capacity or vacancies remain `null`, never zero.

## Provenance

Every source has an explicit origin: `VERIFIED_REAL`, `UNVERIFIED_REAL`,
`SIMULATED_POLICY`, or `UNKNOWN`. A verified source requires both a URL and a
timezone-aware retrieval timestamp. Generated entities require generator
version, seed, and source rule IDs.

## Configuration

The prepared `.env.example` uses `EXECUTION_MODE=fixture`, so `fixture` is a
supported deterministic local mode alongside `simulation` and `bedrock`.
