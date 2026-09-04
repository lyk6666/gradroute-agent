# Stage 2 Grounding Conventions and Real Data Details

This document consolidates the Stage 2 grounding conventions and the detailed
inventory of the collected real-data layer. It defines evidence, scope, and
safety boundaries; it does not introduce or infer university rules.

## Purpose and scope

The `data/real/` package is the grounded, source-traceable NTU College of
Computing and Data Science (CCDS) data layer for the graduation-exception
prototype. Its snapshot date is 31 August 2026.

“Complete” means complete for the exact official-public scope declared in
`data/real/coverage.json`. It does not mean that the package reproduces NTU's
authenticated student systems. When a value or process is not public, it is
recorded as `PARTIAL`, `UNAVAILABLE`, `UNKNOWN`, or `null`; it is never guessed.

The principal official entry points are:

- [CCDS undergraduate programmes](https://www.ntu.edu.sg/computing/admissions/undergraduate-programmes)
- [CCDS curriculum overview](https://www.ntu.edu.sg/computing/discover-ccds/curriculum)
- [NTU course-content portal](https://wish.wis.ntu.edu.sg/webexe/owa/aus_subj_cont.main)
- [NTU class-schedule portal](https://wish.wis.ntu.edu.sg/webexe/owa/aus_schedule.main)

Every extracted fact has a source ID that resolves through
`data/real/source_manifest.json`.

## Grounding conventions

- Completeness is measured separately for inventory coverage and content
  coverage. A dataset can include every record in its declared public scope
  while remaining content-partial because an official source omits fields.
- Admission-cohort and academic-year documents are versioned separately and
  are never substituted for one another.
- Conflicting official values are retained with their provenance instead of
  being averaged or silently resolved.
- Exact curriculum codes missing from the current catalogue remain raw source
  values; titles, AUs, prerequisites, and availability are not invented.
- Complex prerequisite and exclusion expressions remain available as raw text
  when normalization would change their meaning.
- Blank continuation rows in the public class schedule belong to the preceding
  index; the collector retains both parsed meetings and their raw fields.
- A current timetable row proves only that the public portal exposed that row
  at collection time. It does not prove eligibility, vacancy, waitlist order,
  allocation priority, or future availability.
- Public contact and routing pages identify where a request can be sent; they
  do not establish undocumented final approval authority.
- Publicly retrievable documents carrying a restricted-classification footer
  are represented only through normalized facts, official URLs, and hashes.
  Their raw files are not committed.
- Authenticated facts, student records, live operational state, and exception
  outcomes are not inferred into `data/real/`; later stages may represent them
  only as clearly labelled simulated data.

## Inventory summary

| Dataset | Stored records | Inventory | Content |
| --- | ---: | --- | --- |
| Programmes and named pathways | 22 | `COMPLETE` | `COMPLETE` |
| Curriculum configurations | 23 | `COMPLETE` | `PARTIAL` |
| Course catalogue | 219 courses / 1,035 appearances | `COMPLETE` | `PARTIAL` |
| Course offerings | 210 courses / 2,108 indexes | `COMPLETE` | `PARTIAL` |
| Academic calendar | 1 document / 45 events | `COMPLETE` | `PARTIAL` |
| Registration guidance | 1 document / 16 sections | `COMPLETE` | `PARTIAL` |
| Exception policies | 1 document / 29 sections | `COMPLETE` | `PARTIAL` |
| Approval and routing structure | 1 document / 19 sections | `COMPLETE` | `PARTIAL` |
| Provenance manifest | 48 sources | Exact reverse links | Access-aware |

Inventory completeness means all records returned by the declared public
inventory or query scope are stored. Content remains partial where public
sources omit authenticated rules, live state, or complete cohort details.

## Programme inventory

The 22 records comprise 4 single degrees, 5 double degrees, 9 second-major
pathways, 3 jointly delivered degrees, and 1 part-time degree.

| Code | Kind | CCDS base | Programme/pathway |
| --- | --- | --- | --- |
| `AISC` | Single degree | — | Bachelor of Computing (Hons) in Artificial Intelligence (AI) and Society |
| `CSC` | Single degree | — | Bachelor of Computing (Hons) in Computer Science |
| `CE` | Single degree | — | Bachelor of Engineering (Hons) in Computer Engineering |
| `DSAI` | Single degree | — | Bachelor of Computing (Hons) in Data Science and Artificial Intelligence |
| `BCG` | Double degree | `CSC` | Computer Science and Business (Business Analytics) |
| `BCE` | Double degree | `CE` | Computer Engineering and Business (Business Analytics) |
| `CSEC` | Double degree | `CSC` | Computer Science and Economics |
| `CEEC` | Double degree | `CE` | Computer Engineering and Economics |
| `ACDA` | Double degree | `DSAI` | Accountancy and Data Science and Artificial Intelligence |
| `CSC-ENT` | Second major | `CSC` | Computer Science with Entrepreneurship |
| `CSC-ITP` | Second major | `CSC` | Computer Science with Business (International Trading) |
| `CSC-SUST` | Second major | `CSC` | Computer Science with Sustainability |
| `CE-DANA` | Second major | `CE` | Computer Engineering with Data Analytics |
| `CE-ENT` | Second major | `CE` | Computer Engineering with Entrepreneurship |
| `CE-ITP` | Second major | `CE` | Computer Engineering with Business (International Trading) |
| `CE-SUST` | Second major | `CE` | Computer Engineering with Sustainability |
| `CE-BUS` | Second major | `CE` | Computer Engineering with Business |
| `DSAI-SUST` | Second major | `DSAI` | Data Science and Artificial Intelligence with Sustainability |
| `BACF` | Joint degree | — | Applied Computing in Finance |
| `ECDS` | Joint degree | — | Economics and Data Science |
| `MACS` | Joint degree | — | Mathematical and Computer Sciences |
| `BTECH-COMP` | Part-time degree | — | Bachelor of Technology in Computing |

All except `BTECH-COMP` are full-time records. Programme records describe the
public inventory and do not assert exclusive academic ownership of jointly
delivered courses.

## Curriculum configurations

The package stores 23 configurations because the public sources expose a
Computer Science mainstream Business second-major curriculum in addition to the
22 programme/pathway records. Every configuration is marked `PARTIAL`: a public
curriculum sheet is useful grounding, but it is not an authenticated degree
audit for an individual student.

| Curriculum ID | Programme | Kind | Published graduation AU | Study-plan rows |
| --- | --- | --- | ---: | ---: |
| `curriculum.acda.ay2025-26-public-snapshot` | `ACDA` | Base | 172 | 0 |
| `curriculum.aisc.ay2025-26` | `AISC` | Base | 131 | 46 |
| `curriculum.bacf.ay2025-26-public-snapshot` | `BACF` | Base | 135 | 0 |
| `curriculum.bce.ay2025-26` | `BCE` | Base | 156 | 55 |
| `curriculum.bcg.ay2025-26` | `BCG` | Base | 155 or 156 | 54 |
| `curriculum.btech-comp.2025-public-snapshot` | `BTECH-COMP` | Base | Not publicly stated | 0 |
| `curriculum.ce.ay2025-26` | `CE` | Base | 136 | 48 |
| `curriculum.ce-bus.ay2025-26-indexed` | `CE-BUS` | Overlay | 146 | 0 |
| `curriculum.ce-dana.ay2025-26` | `CE-DANA` | Overlay | 136 | 48 |
| `curriculum.ce-ent.ay2025-26` | `CE-ENT` | Overlay | 141 | 49 |
| `curriculum.ce-itp.ay2025-26-indexed` | `CE-ITP` | Overlay | 146 or 147 | 0 |
| `curriculum.ce-sust.ay2025-26` | `CE-SUST` | Overlay | 144 | 102 |
| `curriculum.ceec.ay2025-26` | `CEEC` | Base | 175 | 118 |
| `curriculum.csc.ay2025-26` | `CSC` | Base | 135 or 136 | 47 |
| `curriculum.csc-business.ay2025-26` | `CSC` | Overlay | 145 or 146 | 102 |
| `curriculum.csc-ent.ay2025-26` | `CSC-ENT` | Overlay | 140 or 141 | 48 |
| `curriculum.csc-itp.ay2025-26` | `CSC-ITP` | Overlay | 146 or 147 | 106 |
| `curriculum.csc-sust.ay2025-26` | `CSC-SUST` | Overlay | 145 or 146 | 102 |
| `curriculum.csec.ay2025-26` | `CSEC` | Base | 174 or 175 | 116 |
| `curriculum.dsai.ay2025-26` | `DSAI` | Base | 131 | 44 |
| `curriculum.dsai-sust.ay2025-26` | `DSAI-SUST` | Overlay | 142 | 47 |
| `curriculum.ecds.ay2025-26` | `ECDS` | Base | 140 | 0 |
| `curriculum.macs.ay2025-26` | `MACS` | Base | 144 | 44 |

The 1,176 study-plan rows preserve source order, year, semester, path label,
raw course code, title, requirement category, AU, notes, and source IDs. There
are 669 typed course references, and every typed reference resolves to a record
in `courses.json`. Generic placeholders such as `SC3xxx/SC4xxx`, internships,
and service-learning slots remain untyped.

Important source conflicts are retained explicitly:

- CE with Data Analytics: revised public index gives 136 AU; an accessible
  legacy PDF gives 156 AU.
- CE with Sustainability: one published PA path contains a 116-AU anomaly;
  144 AU is retained with the anomaly recorded as a gap.
- DSAI with Sustainability: the detailed PDF gives 142 AU while the current
  overview gives 141 AU.
- ACDA: the page states 172 AU while the visible category breakdown accounts
  for 160 AU; the unresolved 12 AU is not invented.
- CE-BUS and CE-ITP are index-only snapshots because the linked detailed PDFs
  were unavailable at collection time.
- ACDA, BACF, and BTech lack a complete cohort-specific public study plan.

## Course catalogue

`courses.json` contains the exact deduplicated AY2026–27 Semester 1 public
query union:

- 57 programme/year and elective-pool matrix queries;
- 39 exact curriculum-course queries;
- 219 course records; and
- 1,035 catalogue appearances.

Each course can store:

- code, title, and AU, including legitimate zero-AU records;
- raw prerequisite text plus normalized simple references;
- exclusion codes and raw exclusion text;
- observed academic year, semester, programme, study year, and query context;
- public programme applicability and documented constraints; and
- field-level completeness and source IDs.

Complex Boolean prerequisite expressions are preserved as raw text instead of
being simplified incorrectly. References to courses outside the collected CCDS
scope remain source-faithful external references.

Twenty-six exact study-plan codes returned no current public course-content
record:

```text
AB1003, BC2407, ET5211, ET5214, HE2001, HE2002, HE3003, HW0002,
MH1101, MH1201, MH1301, MH1820, MH2510, MH3500, ML0015, PS0002,
SC1304, SC2306, SC3021, SC3026, SC3079, SC3910, SC3920, SC4079,
SC4262, SD3920
```

Those codes remain in curriculum rows as raw source text and are not given
invented catalogue metadata.

## Course offerings and indexes

`course_offerings.json` is a timestamped public schedule snapshot built from:

- 55 programme-schedule matrix queries; and
- 438 direct lookups: full-time and part-time requests for all 219 catalogue
  courses.

It contains 210 offered courses and 2,108 distinct indexes. Each index preserves
its meetings, class type, group, parsed and raw day/time, venue, teaching weeks,
remarks, and the programme selectors through which it was observed.

The public schedule does not establish:

- an individual student's eligibility;
- total class capacity;
- current vacancies or waitlist priority;
- programme quotas or allocation priority; or
- a guarantee that the same course will be offered later.

These values remain `null` in real data and belong to the simulated operational
state. Nine catalogue codes returned no conventional timetable row:

```text
CC0005, CE6190, ET0001, ET5213, ML0003, NH0001, SC1003, SC2079,
SC3099
```

No timetable row does not automatically mean that a course is cancelled; it
may be self-paced, project-based, inactive for the term, or represented outside
the conventional schedule.

## Calendar, policies, and routing

`academic_calendar.md` contains 45 events for AY2026–27, including teaching,
recess, revision/examination, vacation, Special Term, CCDS internship and
attachment periods, registration cycles, Add/Drop, schedule releases,
allocation results, result releases, FGO windows, review timing, and
convocation-related cutoffs.

The policy corpus contains:

- 16 registration sections;
- 29 exception, exemption, exchange, ICC, and graduation sections; and
- 19 approval or routing sections.

Sections carry their own source origin and applicability. Cohort handbooks for
AY2023–24 through AY2026–27 remain separate. Current public contact pages prove
where an enquiry is routed, not who has final authority.

The following boundaries remain explicitly unknown or authenticated-only:

- personalised registration times and the detailed current registration guide;
- live capacity, eligibility, waitlist, and allocation logic;
- a general post-Add/Drop registration exception;
- a general prerequisite or timetable-clash waiver outside narrow published
  cases;
- overload and restricted-repeat forms, evidence, approver delegation, and SLA;
- substitution, general BDE appeal, and complete LOA document requirements;
- a universal course-coordinator-to-undergraduate-office approval chain; and
- any guaranteed exception or graduation outcome.

## Provenance and source handling

The 48 manifest entries are classified as follows:

| Access result | Count |
| --- | ---: |
| Retrieved | 42 |
| Partially retrieved | 4 |
| Authentication required | 2 |

| Classification | Count |
| --- | ---: |
| Public | 27 |
| Public but marked restricted | 19 |
| Authenticated | 2 |

Each source records its URL, retrieval/check time, version, temporal scope,
access result, classification, retrieval method, request parameters, checksum
and checksum scope where content was retrieved, access note, and exact reverse
dependencies.

Several publicly downloadable curriculum PDFs contain an NTU
`Classification: Restricted` footer. Their official URLs and source-byte hashes
are recorded, but their raw PDFs are not committed. Authenticated sources have
no fabricated checksum or extracted content.

No real student record or student PII is stored in `data/real/`. Students,
degree-audit outcomes, approvals, transaction results, and mutable capacity or
waitlist state belong in `data/simulated/`.

## Coverage contract

`coverage.json` provides a machine-checkable denominator for all eight real
datasets. It records:

- exact expected record IDs and counts;
- query or discovery scope parameters;
- separately evaluated inventory and content status;
- required fields;
- discovery sources; and
- dimension-specific gaps and affected fields.

Repository validation rejects undeclared records, missing expected records,
unresolved sources, stale reverse dependencies, and unsupported completeness
claims.

## Rebuilding and validating

The committed public portal snapshot can be recollected with network access:

```powershell
.venv\Scripts\python.exe scripts\collect_ntu_course_catalogue.py --output data\real\courses.json --audit-output data\real\course_catalogue_queries.json --curriculum-input data\real\curriculum.json
.venv\Scripts\python.exe scripts\collect_ntu_course_schedules.py --output data\real\course_offerings.json --audit-output data\real\course_schedule_queries.json --catalogue-input data\real\courses.json
.venv\Scripts\python.exe scripts\build_real_data_metadata.py
```

The curriculum builder consumes the ignored local normalization intermediate
`tmp/extracted_curricula.json`; raw restricted PDFs are deliberately not part of
the repository.

Snapshot hashes recorded by the query audits are:

```text
Course catalogue: 3602c59a1b40e6c12ed03b414c22e574958ae9280421e209423c6f04c4d01521
Course schedule:  bb425b22761e27b463d55427c64881d8e5870f709d9dffa7c064f702dfc97a08
```

Validation at the time of this snapshot:

```text
114 tests passed
0 repository consistency errors
297 retained warnings for external prerequisite/exclusion references
```

The warnings preserve real cross-school references; they are not missing local
records that should be silently fabricated.
