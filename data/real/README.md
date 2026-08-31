# Grounded NTU/CCDS data snapshot

This directory is a small, source-traceable input package for the prototype. It is not a complete copy of NTU systems and is not a substitute for current university guidance.

## Scope

- The four primary CCDS undergraduate pathways used by the simulator are AISC, CE, CSC, and DSAI.
- Curriculum category totals are cohort-specific AY2025–26 snapshots. CSC's FYP and coursework alternatives are separate `graduation_paths`; documented MPE counts and level/group constraints are retained. `rules_completeness` remains `PARTIAL`, so these records are not yet sufficient for a full degree audit.
- The course catalogue is a closed four-course subset shared by those curricula. Unknown exclusions and uncollected constraints are explicitly marked `UNKNOWN`.
- Calendar and public registration policy use AY2026–27 sources. A future case must select rules by its own admission cohort and the relevant operating academic year; loaders do not merge these versions.
- Course offerings are an explicit `PLACEHOLDER`. No missing offering, index, vacancy, capacity, or waitlist value is interpreted as zero or as “not offered.”
- The `college` field is a prototype scope label, not an assertion of exclusive programme ownership or delivery.

## Provenance and policy safety

`source_manifest.json` records URLs, retrieval times, effective periods, source origins, and reverse dependencies. The selected dated DSAI cohort sheet is kept separate from a conflicting unversioned overview instead of merging their totals. Policy Markdown declares each section's origin and applicability in an exact JSON metadata block. Repository policy queries require cohort or academic-year context; source-unspecified sections require an explicit opt-in.

Unpublished exception processes remain `UNKNOWN`. If later prototype work invents deterministic workflow rules, every simulated section must begin with the exact banner:

```text
SIMULATED POLICY FOR PROTOTYPE
```

The loader rejects an unlabelled simulated section.

The selected curriculum PDFs are marked restricted by CCDS. This package stores traceable URLs and the minimum extracted facts needed by the prototype, not redistributed PDF copies. Any later collection must preserve source access and handling restrictions.
