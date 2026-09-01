"""Isolated Stage 7 execution, deterministic oracles, and report generation."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import timedelta
from pathlib import Path
from time import perf_counter
from typing import Any

from graduation_exception_agent.data.simulated import (
    load_exception_cases,
    load_scenarios,
)
from graduation_exception_agent.evaluation.execution_contracts import (
    CommittedActionCompletionPredicate,
    EvaluatorExecutionContract,
    RegistrationCompletionPredicate,
    load_execution_contract_package,
)
from graduation_exception_agent.evaluation.models import (
    CAMPAIGN_ID,
    CampaignMetricsSummary,
    CampaignPricing,
    CohortMetrics,
    EvaluationMode,
    EvaluationRunResult,
    EvaluationViolation,
    MEMORY_CONDITIONS,
    MIN_LIVE_SCHEMA_PASS_RATE,
    MemoryCondition,
)
from graduation_exception_agent.memory import (
    ExperienceMemoryRecord,
    RankedInMemoryExperienceMemory,
)
from graduation_exception_agent.models.orchestration import (
    ApprovalPause,
    ApprovalResumePayload,
    ClarificationPause,
    ClarificationResumePayload,
)
from graduation_exception_agent.models.runtime import (
    GoalKind,
    VerifierDecisionCode,
)
from graduation_exception_agent.models.workflow import (
    ApprovalStatus,
    CaseState,
    ExceptionCase,
    ExceptionCaseType,
    ExpectedOutcome,
    Scenario,
    ScenarioFamily,
    ScenarioSplit,
    TransactionAction,
)
from graduation_exception_agent.orchestration import (
    DecisionProvider,
    GroundedDecisionProvider,
    Stage5ControlPlane,
)
from graduation_exception_agent.runtime import ScenarioRuntime, ScenarioRuntimeFactory


_EVALUATOR_ONLY_KEYS = frozenset(
    {
        "evaluator_only",
        "expected_outcome",
        "family",
        "forbidden_transitions",
        "ground_truth",
        "human_routes",
        "injected_event",
        "invalid_paths",
        "loop_expectations",
        "memory_update_permitted",
        "required_transitions",
        "scenario_id",
        "source_artifacts_sha256",
        "split",
        "transaction_script",
        "transaction_script_id",
        "valid_final_paths",
        "valid_initial_paths",
        "verifier_expectations",
    }
)


class Stage7EvaluationCampaign:
    """Run each held-out scenario in a fresh runtime and memory snapshot."""

    def __init__(
        self,
        *,
        data_root: str | Path,
        evaluation_mode: EvaluationMode = EvaluationMode.FIXTURE,
        provider_factory: Callable[[], DecisionProvider] | None = None,
        model_id: str | None = None,
        pricing: CampaignPricing | None = None,
    ) -> None:
        self.data_root = Path(data_root)
        self.evaluation_mode = evaluation_mode
        self.model_id = model_id
        self.pricing = pricing or CampaignPricing()
        if provider_factory is None:
            if evaluation_mode is EvaluationMode.BEDROCK:
                raise ValueError("Bedrock evaluation requires a provider_factory")
            provider_factory = GroundedDecisionProvider
        self._provider_factory = provider_factory
        self._runtime_factory = ScenarioRuntimeFactory.from_data_directory(
            self.data_root
        )
        package = load_execution_contract_package(
            self.data_root / "tests" / "execution_contracts.json"
        )
        self._contracts = package.by_scenario_id
        scenarios = load_scenarios(self.data_root / "tests" / "scenarios.json")
        self._scenarios = {
            str(item.scenario_id): item
            for item in scenarios
            if item.split is ScenarioSplit.EVALUATION
        }
        cases = load_exception_cases(
            self.data_root / "simulated" / "exception_cases.json"
        )
        self._cases = {str(item.case_id): item for item in cases}
        self._validate_inventory()

    @property
    def evaluation_scenario_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._scenarios))

    def run(
        self,
        *,
        scenario_ids: Sequence[str] | None = None,
        repetitions: int = 3,
        on_result: Callable[[EvaluationRunResult], None] | None = None,
    ) -> list[EvaluationRunResult]:
        if repetitions < 1 or repetitions > 3:
            raise ValueError("repetitions must be between 1 and 3")
        selected = (
            self.evaluation_scenario_ids
            if scenario_ids is None
            else tuple(scenario_ids)
        )
        unknown = sorted(set(selected) - set(self._scenarios))
        if unknown:
            raise ValueError(
                "unknown held-out evaluation scenario IDs: " + ", ".join(unknown)
            )
        results: list[EvaluationRunResult] = []
        for scenario_id in selected:
            scenario = self._scenarios[scenario_id]
            contract = self._contracts[scenario_id]
            case = self._cases[str(scenario.case_id)]
            for repetition in range(1, repetitions + 1):
                condition = MEMORY_CONDITIONS[repetition - 1]
                result = self._run_one(
                        scenario=scenario,
                        contract=contract,
                        case=case,
                        repetition=repetition,
                        memory_condition=condition,
                )
                results.append(result)
                if on_result is not None:
                    on_result(result)
        return results

    def summarize(
        self, results: Sequence[EvaluationRunResult]
    ) -> CampaignMetricsSummary:
        ordered = list(results)
        self._require_complete_campaign(ordered)
        passed = sum(item.passed for item in ordered)
        scenarios: dict[str, list[EvaluationRunResult]] = defaultdict(list)
        for item in ordered:
            scenarios[item.scenario_id].append(item)
        three_of_three = sum(
            len(items) == 3 and all(item.passed for item in items)
            for items in scenarios.values()
        )
        total_calls = sum(item.observed_tool_calls for item in ordered)
        successful_calls = sum(item.successful_tool_calls for item in ordered)
        reasoning_calls = sum(item.reasoning_calls for item in ordered)
        reasoning_successes = sum(item.reasoning_successes for item in ordered)
        reasoning_fallbacks = sum(item.reasoning_fallbacks for item in ordered)
        violation_counts = Counter(
            violation.code for item in ordered for violation in item.violations
        )
        recovery = [
            item for item in ordered if item.family is ScenarioFamily.S7_DYNAMIC_FAILURE
        ]
        escalations = [
            item
            for item in ordered
            if item.expected_outcome is ExpectedOutcome.ESCALATED
        ]
        approvals = [
            item for item in ordered if bool(item.approval_transitions)
        ]
        clarifications = [
            item
            for item in ordered
            if item.expected_outcome is ExpectedOutcome.CLARIFICATION_REQUIRED
        ]
        checkpoints = [item for item in ordered if item.checkpoint_paused]
        nonempty_memory = [
            item
            for item in ordered
            if item.memory_condition is not MemoryCondition.EMPTY
        ]
        costs = [
            item.estimated_cost_usd
            for item in ordered
            if item.estimated_cost_usd is not None
        ]
        schema_rate = (
            None
            if reasoning_calls == 0
            else _rate(reasoning_successes, reasoning_calls)
        )
        acceptance_failures: list[str] = []
        if passed != len(ordered):
            acceptance_failures.append("RUN_FAILURES_PRESENT")
        if three_of_three != len(scenarios):
            acceptance_failures.append("SCENARIO_CONSISTENCY_BELOW_TARGET")
        if self.evaluation_mode is EvaluationMode.BEDROCK and (
            schema_rate is None or schema_rate < MIN_LIVE_SCHEMA_PASS_RATE
        ):
            acceptance_failures.append("LIVE_SCHEMA_PASS_RATE_BELOW_THRESHOLD")
        return CampaignMetricsSummary(
            evaluation_mode=self.evaluation_mode,
            model_id=self.model_id,
            scenario_count=105,
            repetitions_per_scenario=3,
            run_count=315,
            passed_runs=passed,
            failed_runs=len(ordered) - passed,
            task_completion_rate=_rate(
                sum(item.task_completed for item in ordered), len(ordered)
            ),
            valid_resolution_rate=_rate(
                sum(item.resolution_valid for item in ordered), len(ordered)
            ),
            constraint_violation_rate=_rate(
                sum(bool(item.violations) for item in ordered), len(ordered)
            ),
            recovery_success_rate=_passing_rate(recovery),
            correct_escalation_rate=_passing_rate(escalations),
            approval_compliance_rate=_clean_code_rate(approvals, "APPROVAL_"),
            clarification_routing_accuracy=_clean_code_rate(
                clarifications, "CLARIFICATION_"
            ),
            checkpoint_resume_integrity=_clean_code_rate(
                checkpoints, "CHECKPOINT_"
            ),
            memory_override_violation_rate=_code_rate(
                nonempty_memory, "MEMORY_OVERRIDE_VIOLATION"
            ),
            memory_write_gate_violation_rate=_code_rate(
                ordered, "MEMORY_WRITE_GATE_VIOLATION"
            ),
            post_action_false_completion_rate=_code_rate(
                ordered, "POST_ACTION_FALSE_COMPLETION"
            ),
            tool_call_success_rate=_rate(successful_calls, total_calls),
            schema_validation_pass_rate=schema_rate,
            loop_cap_hit_rate=_code_rate(ordered, "LOOP_CAP_EXCEEDED"),
            scenarios_passing_3_of_3=three_of_three,
            scenario_consistency_rate=_rate(three_of_three, len(scenarios)),
            average_tool_calls=_average(
                item.observed_tool_calls for item in ordered
            ),
            average_graph_steps=_average(item.graph_steps for item in ordered),
            average_latency_ms=_average(item.latency_ms for item in ordered),
            total_input_tokens=sum(item.input_tokens for item in ordered),
            total_output_tokens=sum(item.output_tokens for item in ordered),
            total_tokens=sum(item.total_tokens for item in ordered),
            reasoning_calls=reasoning_calls,
            reasoning_successes=reasoning_successes,
            reasoning_fallbacks=reasoning_fallbacks,
            estimated_cost_usd=(round(sum(costs), 8) if costs else None),
            acceptance_passed=not acceptance_failures,
            acceptance_failures=acceptance_failures,
            violation_counts=dict(sorted(violation_counts.items())),
            by_family=_cohort_metrics(ordered, lambda item: item.family.value),
            by_memory_condition=_cohort_metrics(
                ordered, lambda item: item.memory_condition.value
            ),
        )

    def write_reports(
        self,
        results: Sequence[EvaluationRunResult],
        output_directory: str | Path,
    ) -> CampaignMetricsSummary:
        ordered = sorted(results, key=lambda item: (item.scenario_id, item.repetition))
        summary = self.summarize(ordered)
        destination = Path(output_directory)
        destination.mkdir(parents=True, exist_ok=True)
        _write_jsonl(destination / "run_results.jsonl", ordered)
        _write_jsonl(
            destination / "failures.jsonl",
            [item for item in ordered if not item.passed],
        )
        (destination / "metrics_summary.json").write_text(
            json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        _write_scenario_summary(destination / "scenario_summary.csv", ordered)
        return summary

    def _run_one(
        self,
        *,
        scenario: Scenario,
        contract: EvaluatorExecutionContract,
        case: ExceptionCase,
        repetition: int,
        memory_condition: MemoryCondition,
    ) -> EvaluationRunResult:
        started = perf_counter()
        run_id = (
            f"run.stage7.{scenario.scenario_id.lower()}."
            f"r{repetition}.{memory_condition.value}"
        )
        try:
            runtime = self._runtime_factory.build(str(scenario.scenario_id))
            memory = _memory_for(
                memory_condition,
                case=case,
                contract=contract,
            )
            control_plane = Stage5ControlPlane.build(
                tools=runtime.tools,
                decisions=self._provider_factory(),
                memory=memory,
            )
            intake = control_plane.create_intake(
                request_text=str(case.reason),
                problem_type=ExceptionCaseType(case.problem_type),
                received_at=case.scenario_time,
                case_state=CaseState(case.state),
                submission_ready=case.submission_ready,
                unresolved_questions=list(case.unresolved_questions),
            )
            initial = control_plane.start(intake)
            latest = initial
            outcome_state = initial
            checkpoint_resumed = False
            if contract.expected_outcome is ExpectedOutcome.CLARIFICATION_REQUIRED:
                pause = ClarificationPause.model_validate(
                    initial["clarification_pause"]
                )
                latest = control_plane.resume(
                    thread_id=intake.thread_id,
                    payload=ClarificationResumePayload(
                        clarification_id=pause.clarification_id,
                        answers={
                            field: (
                                True
                                if field == "submission_declaration"
                                else "Provided by the student"
                            )
                            for field in pause.missing_fields
                        },
                        impact=pause.impact,
                        responded_at=case.scenario_time + timedelta(minutes=1),
                    ),
                )
                checkpoint_resumed = True
            elif contract.expected_outcome is ExpectedOutcome.PENDING_APPROVAL:
                pause = ApprovalPause.model_validate(initial["approval_pause"])
                latest = control_plane.resume(
                    thread_id=intake.thread_id,
                    payload=ApprovalResumePayload(
                        approval_id=pause.approval_id,
                        expected_version=pause.approval_version,
                        observed_version=pause.approval_version,
                        status=ApprovalStatus.PENDING,
                        observed_at=case.scenario_time + timedelta(minutes=1),
                    ),
                )
                checkpoint_resumed = True
            contract_state = _matching_contract_checkpoint(
                control_plane=control_plane,
                thread_id=intake.thread_id,
                latest=latest,
                contract=contract,
            )
            persisted = dict(control_plane.state(intake.thread_id).values)
            return self._evaluate_run(
                run_id=run_id,
                repetition=repetition,
                memory_condition=memory_condition,
                scenario=scenario,
                contract=contract,
                runtime=runtime,
                memory=memory,
                outcome_state=outcome_state,
                contract_state=contract_state,
                latest=latest,
                persisted=persisted,
                checkpoint_resumed=checkpoint_resumed,
                latency_ms=max(0, round((perf_counter() - started) * 1000)),
            )
        except Exception as exc:
            latency_ms = max(0, round((perf_counter() - started) * 1000))
            violation = EvaluationViolation(
                code="RUNNER_EXCEPTION",
                message=(
                    "The isolated evaluation run raised a normalized exception "
                    f"of type {type(exc).__name__}."
                ),
            )
            signature = _signature(
                actual_outcome=ExpectedOutcome.FAILED,
                violations=[violation],
                trace=[],
                pre_action=[],
                post_action=[],
                counters={},
            )
            return EvaluationRunResult(
                scenario_id=scenario.scenario_id,
                run_id=run_id,
                repetition=repetition,
                memory_condition=memory_condition,
                evaluation_mode=self.evaluation_mode,
                model_id=self.model_id,
                family=scenario.family,
                expected_outcome=contract.expected_outcome,
                actual_outcome=ExpectedOutcome.FAILED,
                task_completed=contract.expected_outcome is ExpectedOutcome.FAILED,
                resolution_valid=False,
                passed=False,
                violations=[violation],
                trace=[],
                observed_tool_calls=0,
                successful_tool_calls=0,
                graph_steps=0,
                replans=0,
                tool_retries=0,
                total_steps=0,
                memory_hits=0,
                memory_candidate_ids=[],
                memory_write_attempted=False,
                memory_write_completed=False,
                approval_transitions=[],
                admin_escalation=False,
                checkpoint_paused=False,
                checkpoint_resumed=False,
                reasoning_calls=0,
                reasoning_successes=0,
                reasoning_fallbacks=0,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                estimated_cost_usd=(0.0 if self.pricing.configured else None),
                latency_ms=latency_ms,
                result_signature=signature,
                error_type=type(exc).__name__,
            )

    def _evaluate_run(
        self,
        *,
        run_id: str,
        repetition: int,
        memory_condition: MemoryCondition,
        scenario: Scenario,
        contract: EvaluatorExecutionContract,
        runtime: ScenarioRuntime,
        memory: RankedInMemoryExperienceMemory,
        outcome_state: Mapping[str, Any],
        contract_state: Mapping[str, Any],
        latest: Mapping[str, Any],
        persisted: Mapping[str, Any],
        checkpoint_resumed: bool,
        latency_ms: int,
    ) -> EvaluationRunResult:
        violations: list[EvaluationViolation] = []
        actual_outcome = _actual_outcome(outcome_state)
        if actual_outcome is not contract.expected_outcome:
            _violate(
                violations,
                "FINAL_OUTCOME_MISMATCH",
                f"Expected {contract.expected_outcome.value}, observed {actual_outcome.value}.",
            )

        trace = _trace_keys(contract_state)
        trace_set = set(trace)
        missing = sorted(set(contract.required_transitions) - trace_set)
        forbidden = sorted(set(contract.forbidden_transitions) & trace_set)
        if missing:
            _violate(
                violations,
                "REQUIRED_TRANSITION_MISSING",
                "Missing required transitions: " + ", ".join(missing),
            )
        if forbidden:
            _violate(
                violations,
                "FORBIDDEN_TRANSITION_OBSERVED",
                "Observed forbidden transitions: " + ", ".join(forbidden),
            )
        if "REQUEST_APPROVAL:SUCCESS->GOAL_COMPLETE" in trace_set:
            _violate(
                violations,
                "APPROVAL_REQUEST_FALSE_COMPLETION",
                "An approval request was incorrectly treated as goal completion.",
            )

        pre_action, post_action = _verifier_sequences(contract_state)
        if pre_action != list(contract.verifier_expectations.pre_action):
            _violate(
                violations,
                "PRE_ACTION_VERIFIER_MISMATCH",
                "Pre-action verifier sequence differs from the frozen oracle.",
            )
        if post_action != list(contract.verifier_expectations.post_action):
            _violate(
                violations,
                "POST_ACTION_VERIFIER_MISMATCH",
                "Post-action verifier sequence differs from the frozen oracle.",
            )

        # Small clarifications are evaluated at their shortest persisted
        # verifier-resume prefix. A material clarification deliberately resumes
        # through Planner, so its one expected replan is observable only after
        # that resumed planner node executes.
        counter_state = (
            latest
            if contract.clarification.required
            and contract.clarification.impact is not None
            and contract.clarification.impact.value == "MATERIAL"
            else contract_state
        )
        counters = counter_state.get("loop_counters", {})
        replans = _nonnegative_int(counters.get("replans"))
        retries = _nonnegative_int(counters.get("tool_retries"))
        total_steps = _nonnegative_int(counters.get("total_steps"))
        if (
            replans != contract.loop_expectations.expected_replans
            or retries != contract.loop_expectations.expected_tool_retries
        ):
            _violate(
                violations,
                "LOOP_EXPECTATION_MISMATCH",
                "Observed replan or retry counters differ from the oracle.",
            )
        if latest.get("limit_reason"):
            _violate(
                violations,
                "LOOP_CAP_EXCEEDED",
                "The run exhausted a configured loop cap.",
            )

        checkpoint_paused = bool(outcome_state.get("__interrupt__"))
        expected_interrupt = (
            contract.checkpoint.pause_required or contract.clarification.required
        )
        if checkpoint_paused != expected_interrupt:
            _violate(
                violations,
                "CHECKPOINT_PAUSE_MISMATCH",
                "The expected persisted pause did not match the observed interrupt.",
            )
        if expected_interrupt and not checkpoint_resumed:
            _violate(
                violations,
                "CHECKPOINT_RESUME_MISSING",
                "A pending approval checkpoint was not safely resumed and re-read.",
            )

        clarification = contract_state.get("clarification_pause", {})
        clarification_impact = (
            str(clarification.get("impact"))
            if isinstance(clarification, Mapping) and clarification
            else None
        )
        clarification_resume = (
            str(clarification.get("resume_target"))
            if isinstance(clarification, Mapping) and clarification
            else None
        )
        if contract.clarification.required:
            expected_impact = contract.clarification.impact
            expected_resume = contract.clarification.resume_target
            if (
                expected_impact is None
                or clarification_impact is None
                or not clarification_impact.startswith(expected_impact.value)
            ):
                _violate(
                    violations,
                    "CLARIFICATION_IMPACT_MISMATCH",
                    "Clarification impact differs from the frozen oracle.",
                )
            runtime_resume = {
                "PLANNER": "PLANNER",
                "VERIFIER_PRE_ACTION": "PRE_ACTION_VERIFIER",
            }.get(expected_resume.value if expected_resume is not None else "")
            if runtime_resume is None or clarification_resume != runtime_resume:
                _violate(
                    violations,
                    "CLARIFICATION_RESUME_MISMATCH",
                    "Clarification resumed at the wrong control-plane node.",
                )

        receipts = list(runtime.evaluator.receipts())
        receipt_ids = [item.receipt_id for item in receipts]
        if len(receipt_ids) != len(set(receipt_ids)) or any(
            item.replayed for item in receipts
        ):
            _violate(
                violations,
                "TRANSACTION_REPLAY_VIOLATION",
                "Action receipts were duplicated or replayed in one isolated run.",
            )
        for receipt in receipts:
            if receipt.action is TransactionAction.REQUEST_APPROVAL and (
                not receipt.intermediate or receipt.goal_effect
            ):
                _violate(
                    violations,
                    "APPROVAL_INTERMEDIATE_VIOLATION",
                    "An approval request receipt was not kept intermediate.",
                )

        predicate_satisfied = _completion_predicate_satisfied(
            runtime=runtime,
            state=latest,
            contract=contract,
        )
        if predicate_satisfied != contract.goal.expected_satisfied:
            _violate(
                violations,
                "FINAL_STATE_PREDICATE_MISMATCH",
                "The direct runtime predicate differs from the expected final state.",
            )
        final = latest.get("final_outcome")
        if (
            isinstance(final, Mapping)
            and final.get("status") == "DONE"
            and not predicate_satisfied
        ):
            _violate(
                violations,
                "POST_ACTION_FALSE_COMPLETION",
                "DONE was emitted without a satisfied direct runtime predicate.",
            )

        memory_attempted = any(
            item.endswith("->MEMORY_UPDATER") for item in trace
        )
        if memory_attempted != contract.memory_update_permitted:
            _violate(
                violations,
                "MEMORY_WRITE_GATE_VIOLATION",
                "Memory update execution differs from verified-DONE permission.",
            )
        if list(_find_evaluator_only_keys(persisted)):
            _violate(
                violations,
                "EVALUATOR_LEAKAGE",
                "Evaluator-only fields appeared in persisted agent state.",
            )

        advisory = latest.get("advisory_memories", [])
        memory_ids = sorted(
            {
                str(item["memory_id"])
                for item in advisory
                if isinstance(item, Mapping) and item.get("memory_id")
            }
        )
        tool_results = latest.get("tool_results", {})
        result_values = (
            list(tool_results.values())
            if isinstance(tool_results, Mapping)
            else []
        )
        observed_calls = len(result_values) + len(receipts)
        successful_calls = sum(
            isinstance(item, Mapping) and item.get("status") == "SUCCESS"
            for item in result_values
        ) + sum(item.status.value == "SUCCESS" for item in receipts)

        reasoning = latest.get("reasoning_audit", [])
        reasoning_items = [
            item for item in reasoning if isinstance(item, Mapping)
        ]
        reasoning_calls = sum(
            item.get("status") in {"SUCCESS", "FALLBACK"}
            for item in reasoning_items
        )
        reasoning_successes = sum(
            item.get("status") == "SUCCESS" for item in reasoning_items
        )
        reasoning_fallbacks = sum(
            item.get("status") == "FALLBACK" for item in reasoning_items
        )
        input_tokens = sum(_usage_int(item, "input_tokens") for item in reasoning_items)
        output_tokens = sum(
            _usage_int(item, "output_tokens") for item in reasoning_items
        )
        total_tokens = input_tokens + output_tokens
        cost = _estimated_cost(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            pricing=self.pricing,
        )
        approval_transitions = [
            item
            for item in trace
            if "APPROVAL" in item or "PAUSE_CHECKPOINT" in item
        ]
        admin_escalation = any("HUMAN_ADMIN_REVIEW" in item for item in trace)
        task_completed = actual_outcome is contract.expected_outcome
        resolution_valid = not violations
        signature = _signature(
            actual_outcome=actual_outcome,
            violations=violations,
            trace=trace,
            pre_action=pre_action,
            post_action=post_action,
            counters=counters if isinstance(counters, Mapping) else {},
        )
        return EvaluationRunResult(
            scenario_id=scenario.scenario_id,
            run_id=run_id,
            repetition=repetition,
            memory_condition=memory_condition,
            evaluation_mode=self.evaluation_mode,
            model_id=self.model_id,
            family=scenario.family,
            expected_outcome=contract.expected_outcome,
            actual_outcome=actual_outcome,
            task_completed=task_completed,
            resolution_valid=resolution_valid,
            passed=task_completed and resolution_valid,
            violations=violations,
            required_transitions_missing=missing,
            forbidden_transitions_observed=forbidden,
            trace=trace,
            verifier_pre_action=pre_action,
            verifier_post_action=post_action,
            observed_tool_calls=observed_calls,
            successful_tool_calls=successful_calls,
            graph_steps=len(trace),
            replans=replans,
            tool_retries=retries,
            total_steps=total_steps,
            memory_hits=len(memory_ids),
            memory_candidate_ids=memory_ids,
            memory_write_attempted=memory_attempted,
            memory_write_completed=bool(latest.get("memory_write_completed")),
            approval_transitions=approval_transitions,
            admin_escalation=admin_escalation,
            clarification_impact=clarification_impact,
            clarification_resume_target=clarification_resume,
            checkpoint_paused=checkpoint_paused,
            checkpoint_resumed=checkpoint_resumed,
            reasoning_calls=reasoning_calls,
            reasoning_successes=reasoning_successes,
            reasoning_fallbacks=reasoning_fallbacks,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=cost,
            latency_ms=latency_ms,
            result_signature=signature,
        )

    def _validate_inventory(self) -> None:
        if len(self._scenarios) != 105:
            raise ValueError(
                f"Stage 7 requires 105 held-out scenarios; found {len(self._scenarios)}"
            )
        family_counts = Counter(item.family for item in self._scenarios.values())
        if set(family_counts.values()) != {15} or len(family_counts) != 7:
            raise ValueError(
                "Stage 7 requires exactly 15 held-out cases in each of 7 families"
            )
        missing_contracts = sorted(set(self._scenarios) - set(self._contracts))
        if missing_contracts:
            raise ValueError(
                "held-out scenarios lack execution contracts: "
                + ", ".join(missing_contracts)
            )

    def _require_complete_campaign(
        self, results: Sequence[EvaluationRunResult]
    ) -> None:
        if len(results) != 315:
            raise ValueError("canonical Stage 7 reporting requires exactly 315 runs")
        expected = {
            (scenario_id, repetition)
            for scenario_id in self.evaluation_scenario_ids
            for repetition in range(1, 4)
        }
        actual = {(item.scenario_id, item.repetition) for item in results}
        if actual != expected or len(actual) != len(results):
            raise ValueError("campaign results do not cover each scenario exactly 3 times")
        for scenario_id in self.evaluation_scenario_ids:
            conditions = {
                item.memory_condition
                for item in results
                if item.scenario_id == scenario_id
            }
            if conditions != set(MEMORY_CONDITIONS):
                raise ValueError(
                    f"scenario {scenario_id} does not cover all memory conditions"
                )


def _memory_for(
    condition: MemoryCondition,
    *,
    case: ExceptionCase,
    contract: EvaluatorExecutionContract,
) -> RankedInMemoryExperienceMemory:
    if condition is MemoryCondition.EMPTY:
        return RankedInMemoryExperienceMemory()
    if condition is MemoryCondition.RELEVANT:
        strategy = "Re-read the available tools and verify the goal after action."
        failed = ["Do not assume a prior route remains applicable."]
        tags = ["relevant", "revalidate"]
    else:
        strategy = "Prefer the familiar prior route before reviewing the tools."
        failed = ["A familiar route may appear faster than renewed verification."]
        tags = ["misleading", "revalidate"]
    record = ExperienceMemoryRecord(
        memory_id=f"memory.seed.{condition.value}",
        case_type=case.problem_type.value,
        goal_kind=GoalKind(contract.goal.kind.value),
        successful_strategy=strategy,
        recovery_steps=["Re-check evidence before any consequential action."],
        failed_strategy_patterns=failed,
        applicability="Advisory pattern for similar exception cases only.",
        tags=tags,
        verification_receipt_ids=["receipt.advisory.seed.1"],
        verified_at=case.scenario_time - timedelta(days=30),
    )
    return RankedInMemoryExperienceMemory([record])


def _matching_contract_checkpoint(
    *,
    control_plane: Stage5ControlPlane,
    thread_id: str,
    latest: Mapping[str, Any],
    contract: EvaluatorExecutionContract,
) -> dict[str, Any]:
    candidates = [dict(latest)]
    candidates.extend(
        dict(snapshot.values) for snapshot in control_plane.history(thread_id)
    )
    required = set(contract.required_transitions)
    forbidden = set(contract.forbidden_transitions)
    matches = [
        candidate
        for candidate in candidates
        if required <= set(_trace_keys(candidate))
        and not (forbidden & set(_trace_keys(candidate)))
    ]
    if not matches:
        raise ValueError("no persisted checkpoint matches the frozen contract")
    return min(matches, key=lambda item: len(_trace_keys(item)))


def _actual_outcome(state: Mapping[str, Any]) -> ExpectedOutcome:
    status = state.get("run_status")
    if status == "WAITING_FOR_CLARIFICATION":
        return ExpectedOutcome.CLARIFICATION_REQUIRED
    if status == "WAITING_FOR_APPROVAL":
        return ExpectedOutcome.PENDING_APPROVAL
    final = state.get("final_outcome")
    if isinstance(final, Mapping):
        final_status = final.get("status")
        if final_status == "DONE":
            return ExpectedOutcome.RESOLVED
        if final_status == "ADMIN_HANDOFF":
            return ExpectedOutcome.ESCALATED
    return ExpectedOutcome.FAILED


def _trace_keys(state: Mapping[str, Any]) -> list[str]:
    return [
        str(item["transition_key"])
        for item in state.get("trace", [])
        if isinstance(item, Mapping) and item.get("transition_key")
    ]


def _verifier_sequences(
    state: Mapping[str, Any],
) -> tuple[list[VerifierDecisionCode], list[VerifierDecisionCode]]:
    pre: list[VerifierDecisionCode] = []
    post: list[VerifierDecisionCode] = []
    for item in state.get("verification_history", []):
        if not isinstance(item, Mapping):
            continue
        decision = VerifierDecisionCode(str(item["decision"]))
        if item.get("phase") == "PRE_ACTION":
            pre.append(decision)
        elif item.get("phase") == "POST_ACTION":
            post.append(decision)
    return pre, post


def _completion_predicate_satisfied(
    *,
    runtime: ScenarioRuntime,
    state: Mapping[str, Any],
    contract: EvaluatorExecutionContract,
) -> bool:
    predicate = contract.goal.completion_predicate
    if isinstance(predicate, RegistrationCompletionPredicate):
        registration = runtime.evaluator.registration()
        return any(
            item.course_code == predicate.expected.course_code
            and (
                predicate.expected.offering_state_id is None
                or item.offering_state_id == predicate.expected.offering_state_id
            )
            for item in registration.registered_courses
        )
    if isinstance(predicate, CommittedActionCompletionPredicate):
        candidate = state.get("action_candidate", {})
        expected_parameters = predicate.expected.action_parameters
        candidate_parameters = (
            candidate.get("parameters", {})
            if isinstance(candidate, Mapping)
            else {}
        )
        parameters_match = all(
            candidate_parameters.get(key) == value
            for key, value in expected_parameters.items()
        )
        return parameters_match and any(
            receipt.case_id == predicate.subject_id
            and receipt.action is predicate.expected.action
            and receipt.committed
            and receipt.goal_effect
            for receipt in runtime.evaluator.receipts()
        )
    raise TypeError("unsupported completion predicate")


def _find_evaluator_only_keys(
    value: Any, path: str = "$"
) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            nested_path = f"{path}.{key_text}"
            if key_text.casefold() in _EVALUATOR_ONLY_KEYS:
                yield nested_path
            yield from _find_evaluator_only_keys(nested, nested_path)
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            yield from _find_evaluator_only_keys(nested, f"{path}[{index}]")


def _usage_int(item: Mapping[str, Any], field: str) -> int:
    usage = item.get("usage")
    if not isinstance(usage, Mapping):
        return 0
    return _nonnegative_int(usage.get(field))


def _nonnegative_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _estimated_cost(
    *, input_tokens: int, output_tokens: int, pricing: CampaignPricing
) -> float | None:
    if not pricing.configured:
        return None
    value = (
        input_tokens * pricing.input_usd_per_million_tokens
        + output_tokens * pricing.output_usd_per_million_tokens
    ) / 1_000_000
    return round(value, 8)


def _violate(
    violations: list[EvaluationViolation], code: str, message: str
) -> None:
    if code not in {item.code for item in violations}:
        violations.append(EvaluationViolation(code=code, message=message))


def _signature(
    *,
    actual_outcome: ExpectedOutcome,
    violations: Sequence[EvaluationViolation],
    trace: Sequence[str],
    pre_action: Sequence[VerifierDecisionCode],
    post_action: Sequence[VerifierDecisionCode],
    counters: Mapping[str, Any],
) -> str:
    payload = {
        "actual_outcome": actual_outcome.value,
        "violations": [item.code for item in violations],
        "trace": list(trace),
        "pre_action": [item.value for item in pre_action],
        "post_action": [item.value for item in post_action],
        "counters": dict(counters),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _rate(numerator: int, denominator: int) -> float:
    return 1.0 if denominator == 0 else round(numerator / denominator, 6)


def _average(values: Iterable[int]) -> float:
    collected = list(values)
    return 0.0 if not collected else round(sum(collected) / len(collected), 3)


def _passing_rate(items: Sequence[EvaluationRunResult]) -> float:
    return _rate(sum(item.passed for item in items), len(items))


def _code_rate(items: Sequence[EvaluationRunResult], code: str) -> float:
    hits = sum(
        any(violation.code == code for violation in item.violations)
        for item in items
    )
    return _rate(hits, len(items)) if items else 0.0


def _clean_code_rate(items: Sequence[EvaluationRunResult], prefix: str) -> float:
    clean = sum(
        not any(violation.code.startswith(prefix) for violation in item.violations)
        for item in items
    )
    return _rate(clean, len(items))


def _cohort_metrics(
    items: Sequence[EvaluationRunResult],
    key: Callable[[EvaluationRunResult], str],
) -> dict[str, CohortMetrics]:
    groups: dict[str, list[EvaluationRunResult]] = defaultdict(list)
    for item in items:
        groups[key(item)].append(item)
    return {
        name: CohortMetrics(
            run_count=len(group),
            passed_runs=sum(item.passed for item in group),
            pass_rate=_passing_rate(group),
            average_graph_steps=_average(item.graph_steps for item in group),
            average_tool_calls=_average(item.observed_tool_calls for item in group),
            average_latency_ms=_average(item.latency_ms for item in group),
        )
        for name, group in sorted(groups.items())
    }


def _write_jsonl(path: Path, items: Sequence[EvaluationRunResult]) -> None:
    content = "".join(item.model_dump_json() + "\n" for item in items)
    path.write_text(content, encoding="utf-8")


def _write_scenario_summary(
    path: Path, results: Sequence[EvaluationRunResult]
) -> None:
    grouped: dict[str, list[EvaluationRunResult]] = defaultdict(list)
    for item in results:
        grouped[item.scenario_id].append(item)
    fieldnames = [
        "scenario_id",
        "family",
        "expected_outcome",
        "passed_runs",
        "consistency",
        "empty_passed",
        "relevant_passed",
        "misleading_passed",
        "average_tool_calls",
        "average_graph_steps",
        "average_latency_ms",
        "total_tokens",
        "violation_codes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for scenario_id, items in sorted(grouped.items()):
            by_memory = {item.memory_condition.value: item for item in items}
            passed = sum(item.passed for item in items)
            writer.writerow(
                {
                    "scenario_id": scenario_id,
                    "family": items[0].family.value,
                    "expected_outcome": items[0].expected_outcome.value,
                    "passed_runs": passed,
                    "consistency": f"{passed}/3",
                    "empty_passed": by_memory["empty"].passed,
                    "relevant_passed": by_memory["relevant"].passed,
                    "misleading_passed": by_memory["misleading"].passed,
                    "average_tool_calls": _average(
                        item.observed_tool_calls for item in items
                    ),
                    "average_graph_steps": _average(
                        item.graph_steps for item in items
                    ),
                    "average_latency_ms": _average(item.latency_ms for item in items),
                    "total_tokens": sum(item.total_tokens for item in items),
                    "violation_codes": "|".join(
                        sorted(
                            {
                                violation.code
                                for item in items
                                for violation in item.violations
                            }
                        )
                    ),
                }
            )


__all__ = ["Stage7EvaluationCampaign"]
