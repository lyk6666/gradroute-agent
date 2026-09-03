# Graduation Exception Agent

The Graduation Exception Agent is a research prototype for resolving complex
graduation and course-registration exceptions within NTU's College of
Computing and Data Science (CCDS).

It is designed for cases in which a final-year student discovers an academic
or registration issue after normal registration has closed. The system brings
together curriculum requirements, prerequisites, course availability,
registration policy, supporting evidence and approval requirements to produce
a grounded, verifiable resolution path.

This repository is not an official NTU service. It combines public NTU/CCDS
sources with simulated student and operational records for research,
demonstration and evaluation.

## Product capabilities

- scenario-based and manual case intake;
- curriculum and degree-audit analysis across CCDS programmes;
- prerequisite, exclusion, semester-offering, timetable and workload checks;
- policy retrieval and exception-eligibility assessment;
- explicit clarification, administrative-review and human-approval gates;
- bounded registration and exception transactions with observable outcomes;
- pre-action and post-action verification;
- working, thread and advisory long-term memory with provenance labels;
- a visual execution graph with visit-by-visit history, a human-readable timeline
  and a verified final response;
- case-specific Bedrock explanations of node activity, working state and memory;
- read-only grounded-data and evaluation dashboards.

## System architecture

The backend is a typed Python application built around FastAPI, LangGraph and
an isolated tool/runtime boundary. It supports deterministic fixture execution
and grounded Amazon Bedrock reasoning through the Converse API.

The frontend is a React application built with Next-compatible routing,
Vinext and Vite. It provides three product surfaces:

- **Main** — case intake and live agent execution;
- **Data** — processed views of real and simulated grounding data;
- **Evaluation** — isolated fixture and Bedrock evaluation evidence.

Evaluator-only ground truth is excluded from the agent's runtime context.
Actions requiring approval cannot be self-approved, and final outcomes are
shown only after verification.

## Data boundary

The grounded package covers public NTU/CCDS curricula, courses, academic
calendar information and published policies. Student records, live offerings,
transactions, exception cases and approval states are simulated.

Authenticated curriculum plans, personalised registration slots, real-time
vacancies and undocumented approval chains are outside the prototype's
authoritative scope. See [`docs/README.md`](docs/README.md) for the detailed
implementation specifications, source conventions and development records.

## Repository structure

```text
data/        grounded public sources, simulated records and scenarios
docs/        architecture, data specifications and development records
evaluation/  accepted fixture and Bedrock evaluation artifacts
frontend/    React/Vinext user interface
scripts/     data, evaluation and delivery utilities
src/         Python backend and agent runtime
tests/       automated backend and contract tests
```

## Prerequisites

- Python 3.11 or newer;
- Node.js 22.13 or newer and npm;
- AWS CLI v2 plus an IAM Identity Center profile when using Bedrock.

## Initial setup

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Install the frontend dependencies:

```powershell
cd frontend
npm ci
cd ..
```

The default `fixture` execution mode does not require AWS credentials. For
Bedrock, configure `.env` with a refreshable AWS profile rather than temporary
access keys:

```dotenv
EXECUTION_MODE=bedrock
AWS_PROFILE=ccds-sandbox
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=amazon.nova-micro-v1:0
UI_NARRATION_ENABLED=1
```

Natural-language UI narration runs whenever it is enabled and a Bedrock model
is configured. This can be used with either fixture or Bedrock control-plane
execution; narration explains recorded results but cannot change them.

Sign in when the overall SSO session has expired:

```powershell
aws sso login --profile ccds-sandbox
```

Never commit `.env`, AWS access keys or session tokens.

## Start the application

### Start both services together

The simplest local startup uses the repository-relative PowerShell launcher.
It starts both services with matching API and CORS settings, waits until they
are ready, and stops both when you press Enter:

```powershell
& .\scripts\start_local.ps1
```

The command may be run from any current directory when invoked with the
script's absolute path. Optional ports can be supplied explicitly:

```powershell
& .\scripts\start_local.ps1 -BackendPort 8000 -FrontendPort 5173
```

### Start the backend separately

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m graduation_exception_agent.api
```

The backend starts at `http://127.0.0.1:8000`:

- API documentation: `http://127.0.0.1:8000/docs`
- health check: `http://127.0.0.1:8000/api/v1/health`
- readiness check: `http://127.0.0.1:8000/api/v1/ready`

### Start the frontend separately

For separate-process startup, keep the backend running and open a second
PowerShell terminal:

```powershell
cd frontend
npm run dev
```

The frontend normally starts at `http://localhost:3000`.

If port 3000 is occupied, choose another port and give the backend the same
allowed frontend origin. For example, set
`FRONTEND_ORIGIN=http://localhost:5173` in the root `.env`, restart the backend,
and run:

```powershell
cd frontend
npm run dev -- --port 5173
```

If the API is hosted at a non-default address, set
`NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local` before starting the
frontend.

For a production-like local frontend:

```powershell
cd frontend
npm ci
npm run build
npm run start
```
