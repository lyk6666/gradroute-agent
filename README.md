# Graduation Exception Agent

Production-style proof-of-concept for resolving NTU CCDS graduation and
registration exception cases using grounded academic rules and a deterministic
simulated environment.

The canonical user problem is recorded in [`PROBLEM_STATEMENT.md`](PROBLEM_STATEMENT.md).
The implementation specifications are indexed in [`docs/README.md`](docs/README.md).

## Current stage

Stage 1 establishes the importable Python package, environment-based
configuration, strict domain schemas, source provenance, safe JSON loaders, and
the initial pytest suite. It deliberately contains no LangGraph, simulator,
rule-engine, tool, evaluation, or UI implementation.

## Development setup

Use Python 3.11 or newer:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest
```

Copying `.env.example` to `.env` is optional for schema and loader tests. Never
commit `.env` or real credentials.
