# Stage 2 Grounding Conventions

This note records the ingestion decisions used for the real NTU/CCDS data layer. It does not introduce new university rules.

## Prototype programme scope

The official CCDS programme overview describes four primary undergraduate pathways: Artificial Intelligence and Society (AISC), Computer Engineering (CE), Computer Science (CSC), and Data Science and Artificial Intelligence (DSAI). These are the four programmes used by the simulator specification. Other double-degree, second-major, joint, and part-time pathways remain outside this initial dataset.

`programmes.json` is an additive extension to the original directory proposal. It supplies a validated target for programme references in curricula and courses.
Its `college` value identifies the prototype's CCDS scope; it is not an assertion that a programme has no other provider or academic partner.

## Version separation

The collected detailed curriculum snapshots are for the AY2025–26 admission cohort. The operational calendar and handbook snapshot are AY2026–27. These records coexist because an AY2025–26 student can study during AY2026–27, but the loader never merges or substitutes one version for another. Repository queries can select curriculum by programme, admission cohort, and effective academic year.

Conflicting or superseded official files are not combined. The manifest identifies the selected source and version. Exact current AY2026–27 code-level CCDS curricula are not publicly available in the collected sources and are not invented.

The dated AY2025–26 DSAI cohort sheet reports 61 programme-core AU and 19 BDE AU, while a current unversioned overview reports different category totals. The dated cohort sheet is selected for this cohort and the conflict is recorded in its manifest version; the values are never averaged or substituted. The CSC sheet has two official routes: 135 AU with FYP and 9 MPE courses, or 136 AU with 3 additional MPE courses replacing FYP. They are represented as separate `graduation_paths`, including the corresponding 35/36 MPE AU and 9/12 MPE course counts.

## Partial and unknown data

- Curriculum records contain verified category AU totals and selected documented MPE constraints, but not every course-level rule, so `rules_completeness` is `PARTIAL`. Uncollected course lists and count constraints are `UNKNOWN`/`null`, never empty or zero assertions.
- The course catalogue is a closed four-course subset. Prerequisites in that subset are transitively resolved; uncollected exclusions and constraints are `UNKNOWN`.
- `course_offerings.json` is a typed `PLACEHOLDER` because a stable, reproducible offering/capacity/waitlist snapshot has not been collected.
- Personalised registration timestamps, general after-Add/Drop exceptions, most prerequisite-waiver workflows, and delegated approval chains remain explicit `UNKNOWN` sections.

Empty and zero are never used as substitutes for unknown values.

## Markdown provenance contract

`academic_calendar.md` and every file in `public_policies/` begin with one exact `GEA-METADATA` JSON comment. Policy metadata declares each level-two section ID, origin, and source IDs. The parser then maps those declarations to headings of the form:

```markdown
## [policy.registration.stars] Official registration channel
```

It preserves the raw Markdown, SHA-256 digest, and source line range. It rejects untracked headings, missing metadata, duplicate IDs, and filename/type mismatches.

A section with origin `SIMULATED_POLICY` must start with the exact visible line:

```text
SIMULATED POLICY FOR PROTOTYPE
```

Policy metadata also declares whether applicability is explicit, source-unspecified, or unknown. An explicit scope carries typed academic-year and/or admission-cohort values. Repository policy queries require one of those contexts; source-unspecified rules are excluded unless the caller opts in. Verified-only queries return only sections whose explicit origin is `VERIFIED_REAL`; they never infer provenance or applicability from wording.

## Cross-file validation

Loading has two phases:

1. strict UTF-8, JSON, Markdown, and Pydantic schema validation;
2. aggregated consistency checks across files.

The second phase checks source IDs and source types, source origins, reverse dependencies, parent/child source declarations, policy applicability, programme/cohort alignment, fixed and alternative curriculum AU totals, curriculum course references, catalogue prerequisite/exclusion closure, programme categories, and offering course references. Public file loaders require the parsed source registry; the repository constructor validates in-memory bundles as well as directory loads. Repository properties and queries return defensive deep copies, and diagnostic loading with `fail_on_errors=False` retains its issue report. Integrity failures use stable issue codes and do not fall back to guessed records.

## Source handling

The selected CCDS curriculum PDFs carry a restricted classification. The repository records their official URLs, retrieval metadata, and only the extracted facts required by this prototype; it does not redistribute local copies. Future collection must preserve any source access and handling restrictions.
