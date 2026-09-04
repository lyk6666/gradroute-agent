# Stage 6 — Grounded LLM Reasoning

## 1. Status and purpose

Stage 6 adds an Amazon Bedrock reasoning adapter and richer advisory-memory
ranking without changing the Stage 5 graph, transaction authority, approval
boundary, or evaluator separation.

The implementation and its offline, fixture, and live verification gates are
complete. On 31 August 2026, the configured Amazon Nova model passed the
opt-in integration test with two real Bedrock requests: specialist selection
and conservative pre-action review.

Stage 6 provides:

- a Boto3 `bedrock-runtime` Converse client;
- forced, schema-described tool output for Amazon Nova;
- typed specialist-selection and pre-action-review responses;
- a grounded prompt projection that excludes evaluator controls and personal
  student identifiers;
- deterministic safety dominance over every model proposal;
- bounded model-call audit metadata in LangGraph checkpoints;
- deterministic exact-plus-related advisory-memory ranking; and
- offline provider, protocol, privacy, fallback, graph, and ranking tests plus
  one explicitly opt-in live test that makes two API requests.

## 2. Configuration boundary

`.env.example` deliberately keeps:

```text
EXECUTION_MODE=fixture
RUN_BEDROCK_LIVE_TESTS=0
```

Normal unit, scenario-matrix, and full-suite runs therefore never make a paid
or networked request. `decision_provider_from_settings(...)` returns the Stage
5 deterministic provider unless `EXECUTION_MODE=bedrock` is explicitly set.
The live test additionally requires the process-level opt-in
`RUN_BEDROCK_LIVE_TESTS=1`.

Credentials are loaded only when `BedrockConverseClient.from_settings(...)` is
called. They are passed to a Boto3 session through `SecretStr` values and are
never logged, checkpointed, included in exceptions, or committed. `.env`
remains covered by `.gitignore`.

## 3. Bedrock structured-output protocol

`BedrockConverseClient` calls `bedrock-runtime.converse` with:

- the configured model ID, region, temperature, and token cap;
- one system instruction;
- one canonical JSON user payload;
- one tool specification with a top-level JSON object schema; and
- `toolChoice.tool`, forcing the named response tool.

Exactly one matching `toolUse` block is accepted. The returned `input` object
is then validated again with the relevant Pydantic model. Missing, duplicate,
unstructured, malformed, or unavailable model output raises a normalized
reasoning error and is never treated as a decision.

This follows the official [Bedrock Converse API](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html),
[Amazon Nova Converse guidance](https://docs.aws.amazon.com/nova/latest/userguide/using-converse-api.html),
and [Nova tool-use schema](https://docs.aws.amazon.com/nova/latest/userguide/tool-use-definition.html).

## 4. Grounded prompt projection

The full workflow state is never sent to the model. Specialist selection sees
only:

- typed problem type;
- goal kinds;
- submission readiness and declared unresolved fields; and
- deidentified advisory-pattern type, goal, and tags.

Pre-action review sees only:

- the deterministic gate result;
- specialist type and completeness flags;
- policy eligibility, grounded missing-document IDs, and approval-required
  flag;
- candidate action plus evidence/version counts; and
- allowlisted Stage 4 tool-result names, statuses, provenance origins, and
  version counts.

The projection does not traverse arbitrary state. Scenario ID/family, expected
outcome, ground truth, transaction script, injected event, case/student IDs,
raw student record, free-form model output, and non-allowlisted tool results
cannot enter the prompt.

## 5. Deterministic safety dominance

The LLM is a bounded reasoning participant, not an authority.

| Model proposal | Applied behavior |
| --- | --- |
| Remove a deterministic specialist | Rejected; the final selection is the union with the deterministic floor |
| Add a specialist | Allowed; it only causes more current evidence to be read |
| Mark a deterministic non-valid route valid | Impossible; the model is not called for a non-`VALID` deterministic gate |
| Agree with deterministic `VALID` | Deterministic validated assessment is retained |
| Request replan or escalation | Allowed; this narrows the route and remains subject to loop caps |
| Request clarification | Allowed only for fields already grounded in intake or current policy-tool evidence |
| Invent a clarification field | Converted to safe human escalation |
| Return malformed output or fail | Deterministic Stage 5 provider is used |
| Approve, transact, change versions, or write memory | No Stage 6 interface exists for these operations |

Model-generated rationale is validated but not used as academic truth and is
not copied into workflow decisions. Applied workflow reasons remain fixed,
auditable system text.

## 6. Checkpoint audit

The unchanged Stage 5 graph adds one JSON-only `reasoning_audit` channel. Each
entry contains only:

```text
sequence
task
status: SUCCESS | FALLBACK | SKIPPED_SAFETY_GATE
model_id
applied
safety_rule
input/output/total token counts
```

The graph copies this bounded typed surface after planning and pre-action
verification. Prompts, responses, model rationale, credentials, AWS request
IDs, and evaluator controls are absent.

## 7. Advisory-memory ranking

`RankedInMemoryExperienceMemory` retains all Stage 5 privacy, write, and
verified-`DONE` requirements. Retrieval scores active, non-excluded records by:

```text
exact case type     +8
exact goal kind     +5
each matching tag   +2
```

Score, verification time, and memory ID provide deterministic ordering. This
allows a same-goal pattern from a related case type to follow an exact match,
while a record with no relevance signal is excluded. Results remain advisory;
current Stage 4 tools always take precedence.

## 8. Construction

```python
from graduation_exception_agent import (
    ScenarioRuntimeFactory,
    Stage5ControlPlane,
    decision_provider_from_settings,
    load_settings,
)
from graduation_exception_agent.memory import RankedInMemoryExperienceMemory

settings = load_settings()
runtime = ScenarioRuntimeFactory.from_data_directory("data").build("S1-D01")
control_plane = Stage5ControlPlane.build(
    tools=runtime.tools,
    decisions=decision_provider_from_settings(settings),
    memory=RankedInMemoryExperienceMemory(),
)
```

`EXECUTION_MODE=fixture` uses deterministic decisions. Changing it to
`bedrock` constructs the grounded Bedrock provider; the graph and tools are
unchanged.

## 9. Verification gates

Offline Stage 6 gate:

```powershell
.venv\Scripts\python.exe -m pytest -q tests\test_stage6_reasoning.py
```

Two-call live gate (specialist selection and pre-action review):

```powershell
$env:RUN_BEDROCK_LIVE_TESTS='1'
.venv\Scripts\python.exe -m pytest -q tests\test_stage6_bedrock_live.py
```

For a smaller one-request credential/model readiness probe, run:

```powershell
.venv\Scripts\python.exe scripts\check_bedrock_reasoning.py
```

The probe prints only validated decision metadata, token counts, exception
classes, and AWS error codes. It suppresses prompts, raw output, provider error
messages, request IDs, and credentials.

Stage 6 is ready for handoff only when the full repository suite, the 140-case
matrix, deterministic data checks, and both live requests pass. At the Stage 6
checkpoint, the offline full-suite result is `583 passed, 1 live test skipped`;
the 140-case matrix and both deterministic builders pass; and the separately
opted-in live gate reports `1 passed` while exercising both model decisions.

## 10. Stage 7 handoff

Stage 7 owns the frozen 315-run evaluation campaign, including repeated live
reasoning trials, trace conformance, route accuracy, fallback rate, token and
latency reporting, robustness perturbations, and regression thresholds. It may
not weaken deterministic safety dominance, prompt allowlisting, current-tool
precedence, checkpoint audit, approval/version gates, or verified-only memory
writes.
