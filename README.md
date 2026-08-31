# Graduation Exception Agent

Production-style proof-of-concept for resolving NTU CCDS graduation and
registration exception cases using grounded academic rules and a deterministic
simulated environment.

The canonical user problem is recorded in [`PROBLEM_STATEMENT.md`](PROBLEM_STATEMENT.md).
The implementation specifications are indexed in [`docs/README.md`](docs/README.md).

## Current stage

Stage 6 is complete as a grounded Amazon Bedrock reasoning layer over the Stage
5 typed, checkpointed LangGraph control plane. The project provides
forced structured Nova output, deterministic safety dominance, allowlisted
prompt projection, checkpointed reasoning audit metadata, and ranked advisory
memory while retaining the frozen graph topology, selective specialist
routing, pre- and post-action verification,
clarification and pending-approval interrupts, strict approval/admin
separation, bounded loops, advisory memory ports, and canonical traces while
retaining Stage 4's isolated, atomic, idempotent tool boundary and 140
evaluator-only execution contracts.

“Complete” is deliberately scoped to the official-public inventory and query
matrix recorded in `data/real/coverage.json`. Authenticated curriculum plans,
personalised registration slots, capacity, eligibility, general late-registration
workflows, and undocumented approval chains remain explicit gaps. The project
does not yet contain embedding/vector retrieval, a durable production
checkpointer, the 315-run end-to-end evaluation campaign, or a UI. The
configured Amazon Nova model has passed the opt-in two-request live gate for
specialist selection and conservative pre-action review.

The high-level graph is frozen in
[`docs/02_solution_architecture.md`](docs/02_solution_architecture.md). It adds
advisory memory retrieval before planning, verified-only memory updates after
completion, pre- and post-action verification, small/material clarification
routing, and a strict distinction between approval and human/admin escalation.
Its Stage 5 implementation is recorded in
[`docs/stage_5_langgraph_control_plane.md`](docs/stage_5_langgraph_control_plane.md).

Next delivery sequence:

```text
Stage 4  deterministic four-domain tools and isolated transaction runtime (complete)
Stage 5  LangGraph control plane, checkpointing, and memory interfaces (complete)
Stage 6  grounded LLM reasoning and richer advisory-memory ranking (complete)
Stage 7  315-run evaluation and robustness hardening
Stage 8  polished demo/UI and operational delivery
```

See the [Stage 3 simulation data details](docs/stage_3_simulation_data_details.md),
[Stage 4 runtime and tools](docs/stage_4_runtime_and_tools.md), and
[Stage 5 control plane](docs/stage_5_langgraph_control_plane.md), and
[Stage 6 grounded LLM reasoning](docs/stage_6_grounded_llm_reasoning.md) for the
delivered foundations, and the
[Stage 2 grounding conventions](docs/stage_2_grounding_conventions.md) for its
real-data basis and limitations.

## Development setup

Use Python 3.11 or newer:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest
```

Validate and inspect the local grounded package without network access:

```powershell
.venv\Scripts\python.exe -c "from graduation_exception_agent.data.real import RealDataRepository; print(RealDataRepository.from_directory('data/real').programmes)"
```

Rebuild and verify the deterministic Stage 3 package:

```powershell
.venv\Scripts\python.exe scripts\build_simulated_data.py
.venv\Scripts\python.exe scripts\build_simulated_data.py --check
.venv\Scripts\python.exe -c "from graduation_exception_agent.data.real import RealDataRepository; from graduation_exception_agent.data.simulated import SimulatedDataRepository; real = RealDataRepository.from_directory('data/real'); simulated = SimulatedDataRepository.from_directory('data/simulated', real_repository=real); print(len(simulated.consistency_issues))"
```

Verify the Stage 4 execution contracts and focused runtime suite:

```powershell
.venv\Scripts\python.exe scripts\build_execution_contracts.py --check
.venv\Scripts\python.exe -m pytest -q tests\test_stage4_models.py tests\test_execution_contracts.py tests\test_stage4_runtime.py
```

Verify the Stage 5 graph, checkpoint/memory contracts, and all 140 scenario
routes:

```powershell
.venv\Scripts\python.exe -m pytest -q tests\test_stage5_execution_contract_loader.py tests\test_stage5_models_memory.py tests\test_stage5_graph.py tests\test_stage5_safety.py tests\test_stage5_scenario_matrix.py
```

Verify Stage 6 without making a network call:

```powershell
.venv\Scripts\python.exe -m pytest -q tests\test_stage6_reasoning.py
```

With valid temporary AWS credentials, explicitly opt into the two-call Bedrock
gate for specialist selection and pre-action review:

```powershell
$env:RUN_BEDROCK_LIVE_TESTS='1'
.venv\Scripts\python.exe -m pytest -q tests\test_stage6_bedrock_live.py
```

For a one-request credential/model readiness probe instead:

```powershell
.venv\Scripts\python.exe scripts\check_bedrock_reasoning.py
```

Copying `.env.example` to `.env` is optional for schema and loader tests. Never
commit `.env` or real credentials.
