# Graduation Exception Agent

Production-style proof-of-concept for resolving NTU CCDS graduation and
registration exception cases using grounded academic rules and a deterministic
simulated environment.

The canonical user problem is recorded in [`PROBLEM_STATEMENT.md`](PROBLEM_STATEMENT.md).
The implementation specifications are indexed in [`docs/README.md`](docs/README.md).

## Current stage

Stage 2 adds the validated NTU/CCDS real-data ingestion layer: source manifests,
four primary programme records, versioned curriculum snapshots, a closed course
subset, academic-calendar and policy Markdown parsers, immutable repository
queries, and cross-file provenance checks. Unavailable offering and exception
details remain explicit placeholders or `UNKNOWN` values. The project still
deliberately contains no LangGraph, simulator, rule engine, action tools,
evaluation harness, or UI implementation.

The grounding conventions and current limitations are recorded in
[`docs/07_stage_2_grounding_conventions.md`](docs/07_stage_2_grounding_conventions.md).

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

Copying `.env.example` to `.env` is optional for schema and loader tests. Never
commit `.env` or real credentials.
