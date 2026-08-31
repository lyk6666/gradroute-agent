# Stage 2 Grounding Conventions

This note defines the scope and safety boundaries of the NTU/CCDS real-data
layer. It does not introduce university rules.

## Declared completion scope

Stage 2 is complete for the official-public inventory described by
`data/real/coverage.json`, as checked on 31 August 2026. Completeness is assessed
twice: inventory coverage asks whether every record in the declared public
scope is represented; content coverage asks whether every required field is
actually exposed by those sources. The latter may remain `PARTIAL` or
`UNAVAILABLE` without fabricated values.

The measured snapshot contains:

- 22 public CCDS programme/pathway records;
- 23 public curriculum configurations and 1,176 normalized study-plan rows;
- 219 AY2026–27 Semester 1 catalogue records and 1,035 appearances;
- 210 scheduled courses and 2,108 indexes;
- 45 typed calendar events; and
- 64 registration, exception, and approval/routing sections.

## Programme and curriculum boundaries

The programme inventory includes the current public single-degree,
double-degree, second-major, joint-degree, and part-time entries. The 23rd
curriculum configuration is the separately published Computer Science
mainstream Business second-major plan; it is not presented as another degree.

Detailed curricula use exact AY2025–26 cohort sheets where available. Public
page, unversioned PDF, stale-search-index, and authenticated-only cases remain
separate. Conflicts are retained rather than averaged or silently resolved,
including revised versus legacy CE/Data Analytics totals, the CE/Sustainability
path anomaly, and the DSAI/Sustainability PDF versus overview total. Every
configuration is currently `PARTIAL`, because a public curriculum snapshot is
not a complete authenticated degree audit.

## Course catalogue and schedule boundaries

The catalogue collector queries all discovered current degree selectors,
programme years, relevant elective pools, and exact codes appearing in the
published study plans. It preserves raw prerequisite/exclusion expressions,
zero-AU records, external course references, programme appearances, request
hashes, and unresolved exact-code searches. A code absent from the current
portal remains a raw study-plan code; no metadata is invented for it.

The schedule collector combines the programme matrix with direct full-time and
part-time lookups for every collected catalogue code. Blank continuation rows
are attached to their preceding index, and class type, group, raw day/time,
venue, teaching weeks, and remarks are retained. A current schedule row proves
only that the public portal exposed that course/index at the snapshot time. It
does not prove student eligibility, capacity, vacancy, waitlist order,
allocation priority, or future availability.

## Calendar and policy boundaries

Calendar records distinguish exact dates, general timing, and unavailable
personalised timestamps. Policy sections independently declare their origin,
source IDs, and applicability by admission cohort or academic year. Current
contact pages establish routing, not final approval authority. Narrow workflows
such as the exchange-credit prerequisite waiver and CC0006 clash route are not
generalized beyond their published context.

Admission-cohort handbooks are never substituted for one another. AY2023–24,
AY2024–25, AY2025–26, and AY2026–27 are catalogued separately; the unavailable
official-public AY2022–23 handbook remains a coverage gap.

## Explicit public-access gaps

The real layer does not claim public knowledge of personalised registration
slots, authenticated curriculum plans, total class capacity, live eligibility,
waitlist priority, general post-Add/Drop registration, a general prerequisite or
clash waiver, overload/restricted-repeat forms and service times, substitution,
BDE appeal, or a universal coordinator-to-approver chain. These fields remain
`UNKNOWN`, `UNAVAILABLE`, or simulated in later stages.

## Provenance and source handling

Every real record resolves to `source_manifest.json`. Provenance includes URL,
time, access outcome, classification, retrieval method, request parameters,
checksum scope, version, temporal scope, and exact reverse dependencies.
`coverage.json` is itself cross-checked against the loaded IDs and source
quality.

Several curriculum PDFs are publicly retrievable but carry an NTU restricted
classification footer. Only normalized facts, official URLs, and source-byte
hashes are committed. Raw copies stay outside version control.

## Validation

Loading has two phases: strict JSON/Markdown/Pydantic parsing, followed by
cross-file checks for source IDs and types, reverse provenance, programme and
cohort alignment, AU totals and paths, study-plan course references, catalogue
scope, offering references, policy applicability, and completeness-contract
drift. Missing external prerequisite/exclusion targets are preserved as
warnings, not converted into fictional local courses.
