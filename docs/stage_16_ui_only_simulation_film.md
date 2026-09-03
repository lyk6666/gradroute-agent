# Stage 16 — UI-only simulation film

## Approved direction

Replace the decorated screenshot montage with a clean, approximately 115-second
screen demonstration: S7 dynamic registration recovery, then S2 prerequisite
evidence and explicit simulated human approval. No opening, product tour,
seven-case montage, Evaluation closing, captions, badges, vignette, or music.
The application's native simulation/provenance labels remain visible.

## Implementation plan

- Record real browser footage and timestamp the important runtime events.
- Preserve the same page/session between cases; trim inactive waiting without
  fading the screen or resetting the camera at every node.
- Show larger close-ups of requests, findings, approval evidence, and results.
- Use a thin blue/amber outline for the area being discussed, with no dim mask.
- Keep speech to short, case-specific explanations at material milestones.
- Render a 1280×720 review copy first; retain a separate 4K export option.
- Keep the Stage 15 rendered film for comparison and generated media out of Git.

## Verification plan

- Check every selected clip against its actual node/visit and observed outcome.
- Confirm S7 shows the failed first transaction and successful recovery.
- Confirm S2 waits for an explicit simulated reviewer decision and reports the
  actual waiver result, not an unobserved registration result.
- Check narration duration, camera continuity, highlight bounds, and clip bounds.
- Render and inspect actual movie frames, including transitions and approval.

## Progress

- [x] Approved edit and scope recorded
- [x] Continuous browser capture and event manifest implemented
- [x] UI-only Remotion composition and larger camera framing
- [x] Brief narration synchronized to selected moments
- [x] 720p movie rendered and visually reviewed
- [x] Project instructions and verification results updated

## Integration issue found during capture

The first live take exposed a real terminal-notification race: the backend could
set a run to completed before appending its terminal event. An SSE reader could
then close without sending the final snapshot, leaving the frontend on
"Executing current step". Completion/failure status and the terminal event are
now published under the same re-entrant lock. The frontend also rejects older
HTTP snapshots that would overwrite newer streamed state. Two concurrency
regression tests cover both completion and failure.

The capture retains one browser page for both scenarios and verifies that
"Start a new run" is visible after each backend completion. No page reload or
fabricated UI-state change is used to bypass a stuck run.

## Recording and edit contract

- Chrome provides lossless PNG screencast frames to a high-quality H.264 encoder.
  The source is 1920×1080 at 25 fps; the review composition is 1280×720 at 30 fps.
- A shared fixed-rate recording clock timestamps every selected moment. Clip
  identity, node visit, recorded length, and final run status are validated before
  rendering; missing observations cannot fall back to unrelated screenshots.
- Seventeen chronological clips make up exactly 115 seconds. Nine short voice
  lines leave approximately 55 seconds of quiet viewing time.
- The camera carries its previous position forward and eases over 0.85 seconds,
  with close-ups up to 3.15×. Context padding is applied only once.
- Start-button movement, approval evidence scrolling, the explicit Approve click,
  and final-response scrolling are retained as actual recorded UI actions.
- Thin blue outlines identify narrated content; amber identifies the approval
  controls. There are no text overlays, opacity fades, edge masks, or music.

## Completion evidence

- The final review movie is 115.05 seconds and 18,577,795 bytes. It contains
  H.264 video at 1280×720/30 fps and stereo AAC audio at 48 kHz.
- The accepted visual retake executed the deterministic simulation lane in one
  continuous browser session: all 17 required clips were observed, S7 and S2
  completed, and S2 recorded an explicit Approve action. An earlier Bedrock take
  validated the same clip and outcome contract; the local AWS SSO profile was not
  available when the final framing-only retake was made.
- Encoded-frame review covered the S7 request, first failed transaction, S2
  evidence, approval controls, and final response. The final camera movement now
  exposes the case-specific “Why this is valid” reasoning rather than stopping
  on the request summary.
- Video tests validate duration, ordering, clip identity, repeat visits, camera
  continuity, start-button interactions, and the absence of caption/dimming
  layers. Backend concurrency regression tests cover both completed and failed
  terminal delivery. Frontend lint/typecheck pass, as do all nine video tests
  and the 17-test focused runtime suite.
