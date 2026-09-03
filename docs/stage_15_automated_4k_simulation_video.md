# Stage 15 — Automated 4K Simulation Video

## Objective

Produce the simulation portion of the hackathon video from a genuine local
application run while retaining precise editorial control over framing,
timing, captions and narration.

Remotion is the director and renderer, not a substitute implementation of the
product. A controlled browser operates the real frontend and backend first;
the resulting evidence is then edited into the final film.

## Delivered workflow

The repository-level command is:

```powershell
& .\scripts\render_simulation_demo.ps1
```

It performs the following sequence:

1. validates Python, Node, frontend and video dependencies;
2. checks the configured AWS profile when Bedrock mode is active;
3. starts the FastAPI backend and frontend with matching ports and CORS;
4. generates replaceable Singapore-English scene narration;
5. opens the real application in an automated 3840×2160 browser;
6. captures the Main, Data and Evaluation product tour;
7. traverses all seven demo scenario previews;
8. executes S7 and S2 in controlled step-by-step mode;
9. records the S2 simulated human approval as a visible human checkpoint;
10. saves a capture manifest, directed frames and raw browser takes under `video/artifacts/`;
11. renders the Remotion composition as a 4K H.264 MP4; and
12. stops only the services it started in a `finally` cleanup path, while
    leaving a healthy pre-existing frontend/backend pair untouched.

The output is `video/output/simulation-demo-4k.mp4`.

## Film structure

The composition runs at 3840×2160, 30 frames per second and approximately
3 minutes 48 seconds.

| Chapter | Purpose |
| --- | --- |
| Opening | Establish the multi-source nature of a graduation exception. |
| Main Page | Introduce intake, graph, case overview, timeline and verified response. |
| Data Page | Show real-versus-simulated boundaries, records and provenance. |
| Evaluation Page | Show inspectable outcomes and separated evaluation dimensions. |
| Seven scenarios | Establish the breadth of the simulation package. |
| S7 | Demonstrate transaction failure, observation, verification, replanning and recovery. |
| S2 | Demonstrate prerequisite evidence and a non-delegable human approval. |
| Closing evidence | Return to the accepted evaluation surface. |

The narration text is maintained in `video/script/narration.json`. Each scene
is synthesized into an independent audio file so a human recording can replace
one segment without changing the rest of the edit.

## Camera design

The application exposes stable, non-visual `data-demo-target` hooks for its
five Main-page regions and the important Data and Evaluation regions. During
capture, the browser records the actual bounding rectangle of each target.
Remotion calculates a bounded pan and zoom from those rectangles rather than
assuming a fixed screen layout.

For graph execution, each captured state records the scenario, node, visit
number, status and sequence. The S7 direction selects the first transaction,
failed post-action verification, second planner visit and second transaction
independently. The S2 direction selects the audit, policy, course, verifier,
approval, transaction and post-action states. This preserves the distinction
between initial work and a genuine replan.

All movement uses the Remotion frame clock. Camera scale is capped at 2.35×,
important content is held for reading, and captions stay within a consistent
safe area. Blue marks active reasoning, amber marks human authority, red marks
an observed failure and green marks verified completion.

## Truthfulness and safety

The film carries this persistent disclosure:

> Recorded from a real system run using grounded public sources and simulated operational data.

The video layer does not fabricate agent statuses, policy findings, approval
responses or transaction results. S2 approval is explicitly labelled
"Simulated human approval". Evaluator-only ground truth remains outside the
runtime and is shown only through the separate Evaluation surface.

## Operational modes

- Default: respect the repository `.env`, including Bedrock reasoning when configured.
- `-Fixture`: use the deterministic offline control plane.
- `-HeadedCapture`: display the browser while it performs the scripted run.
- `-SkipCapture`: reuse the current capture when changing only the edit.
- `-SkipNarration`: reuse previously generated narration files.

Neural narration requires network access during generation. Bedrock capture
also requires a valid AWS SSO session and model access. Neither condition is
silently replaced with fabricated output.

## Implementation record

- Added a standalone, pinned Remotion and Playwright package under `video/`.
- Added a capture manifest contract and 4K browser recorder.
- Added stable UI targeting hooks without altering visible product behaviour.
- Added the approved eight-part storyboard, captions and narration script.
- Added frame-driven camera motion, status-aware accents and approval callout.
- Added neural narration generation with replaceable scene files.
- Added a repository-relative process orchestrator with readiness checks and cleanup.
- Added project-level startup and render instructions to the root README.

## Validation checklist

- [x] Frontend TypeScript validation
- [x] Frontend lint validation
- [x] Remotion TypeScript validation
- [x] Capture-script JavaScript syntax validation
- [x] Orchestrator PowerShell parser validation
- [x] Pinned dependency installation with no reported npm vulnerability
- [x] Narration generation for all eight chapters
- [x] Automated Bedrock-mode capture of the current live application
- [x] Visual inspection of representative encoded 4K frames
- [x] Complete 4K MP4 render

The validation run captured 81 directed 3840×2160 frames across the product
tour, seven-scenario overview, complete S7 and S2 workflows, and closing
evaluation proof. Both featured workflows reached their intended terminal
state; S2 included an explicit simulated reviewer action.

The resulting H.264 MP4 is 228.053 seconds long and 176,331,074 bytes. It
contains 3840×2160 video at 30 frames per second plus stereo AAC audio at
48 kHz. Frames sampled from the encoded movie at the Main graph, S7 failed
transaction, S2 approval, and closing Evaluation scenes passed visual review.
