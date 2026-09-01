"""Run the canonical 105-case by 3-condition Stage 7 campaign."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from graduation_exception_agent.config import load_settings
from graduation_exception_agent.evaluation import (
    CampaignPricing,
    EvaluationMode,
    Stage7EvaluationCampaign,
)
from graduation_exception_agent.reasoning import (
    BedrockConverseClient,
    GroundedBedrockDecisionProvider,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Execute the frozen 315-run held-out evaluation and write JSONL, "
            "JSON, and CSV reports."
        )
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation"))
    parser.add_argument(
        "--mode",
        choices=[item.value for item in EvaluationMode],
        default=EvaluationMode.FIXTURE.value,
    )
    parser.add_argument("--input-usd-per-million", type=float, default=0.0)
    parser.add_argument("--output-usd-per-million", type=float, default=0.0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    mode = EvaluationMode(args.mode)
    pricing = CampaignPricing(
        input_usd_per_million_tokens=args.input_usd_per_million,
        output_usd_per_million_tokens=args.output_usd_per_million,
    )
    provider_factory = None
    model_id = None
    if mode is EvaluationMode.BEDROCK:
        if os.getenv("RUN_BEDROCK_EVALUATION") != "1":
            raise SystemExit(
                "Set RUN_BEDROCK_EVALUATION=1 to authorize the 315-run live campaign."
            )
        settings = load_settings()
        client = BedrockConverseClient.from_settings(settings)
        provider_factory = lambda: GroundedBedrockDecisionProvider(client=client)
        model_id = settings.bedrock_model_id

    campaign = Stage7EvaluationCampaign(
        data_root=args.data_dir,
        evaluation_mode=mode,
        provider_factory=provider_factory,
        model_id=model_id,
        pricing=pricing,
    )
    progress = {"completed": 0}

    def report_progress(_: object) -> None:
        progress["completed"] += 1
        if progress["completed"] % 15 == 0:
            print(f"completed={progress['completed']}/315", flush=True)

    results = campaign.run(on_result=report_progress)
    summary = campaign.write_reports(results, args.output_dir)
    print(f"runs={summary.run_count}")
    print(f"passed={summary.passed_runs}")
    print(f"failed={summary.failed_runs}")
    print(f"acceptance_passed={summary.acceptance_passed}")
    if summary.acceptance_failures:
        print("acceptance_failures=" + ",".join(summary.acceptance_failures))
    print(f"scenario_consistency_rate={summary.scenario_consistency_rate:.6f}")
    print(f"output_dir={args.output_dir.resolve()}")
    return 0 if summary.acceptance_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
