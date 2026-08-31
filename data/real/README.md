# Grounded NTU/CCDS official-public snapshot

This directory is the complete official-public inventory for the scope declared
in `coverage.json`, as retrieved on 31 August 2026. It is not a copy of
authenticated NTU systems and is not a substitute for current university
guidance.

## Scope

- `programmes.json` contains 22 single-degree, double-degree, second-major,
  joint-degree, and part-time CCDS pathways from the current public programme
  index.
- `curriculum.json` contains 23 public configurations. The extra configuration
  is the published Computer Science mainstream Business second-major plan.
  Detailed rows are principally AY2025–26 snapshots; public-page-only or
  index-only configurations are marked `PARTIAL` and retain their known gaps.
- `courses.json` contains 219 AY2026–27 Semester 1 records and 1,035 observed
  catalogue appearances collected from programme, elective-pool, and exact
  curriculum-course queries. A catalogue appearance is not proof of a class
  offering or individual eligibility.
- `course_offerings.json` contains 210 scheduled courses and 2,108 indexes from
  the public programme matrix plus direct full-time and part-time lookups.
  Capacity, vacancies, waitlist order, quotas, and personal eligibility are not
  present in this source and remain `null` or simulated state.
- `academic_calendar.md` and `public_policies/` cover the public dates, cohort
  handbooks, registration guidance, exception routes, and routing roles needed
  by the case domain. Unpublished processes remain explicit `UNKNOWN` sections.
- `course_catalogue_queries.json` and `course_schedule_queries.json` retain the
  request matrix, per-response hashes, snapshot time, normalized hash, and
  unresolved public-source limitations.

## Provenance and policy safety

`source_manifest.json` records URLs, retrieval/check times, access outcome,
classification, effective period, request method, checksum scope, and exact
reverse dependencies. `coverage.json` separately states the denominator,
inventory status, content status, and field-level gaps for every real dataset.
Policy Markdown declares each section's origin and applicability in an exact
JSON metadata block. Repository policy queries require cohort or academic-year
context; source-unspecified sections require an explicit opt-in.

Unpublished exception processes remain `UNKNOWN`. If later prototype work invents deterministic workflow rules, every simulated section must begin with the exact banner:

```text
SIMULATED POLICY FOR PROTOTYPE
```

The loader rejects an unlabelled simulated section.

Several publicly retrievable curriculum PDFs carry an NTU restricted
classification footer. The repository stores normalized facts, official URLs,
and source-byte hashes, but does not redistribute those PDFs. The local `tmp/`
working directory is ignored to prevent accidental inclusion.

## Rebuild the public portal snapshots

The collectors require network access to NTU's public portals:

```powershell
.venv\Scripts\python.exe scripts\collect_ntu_course_catalogue.py --output data\real\courses.json --audit-output data\real\course_catalogue_queries.json --curriculum-input data\real\curriculum.json
.venv\Scripts\python.exe scripts\collect_ntu_course_schedules.py --output data\real\course_offerings.json --audit-output data\real\course_schedule_queries.json --catalogue-input data\real\courses.json
.venv\Scripts\python.exe scripts\build_real_data_metadata.py
```
