"""Build deterministic provenance and coverage metadata for Stage 2.

The script deliberately derives record inventories and reverse provenance from
the persisted bundle.  It never infers that an inaccessible or authenticated
source was retrieved, and it distinguishes a complete query-result inventory
from incomplete source content.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REAL_ROOT = ROOT / "data" / "real"
AS_OF = "2026-08-31T12:13:00+08:00"
MANUAL_RETRIEVED_AT = "2026-08-31T10:15:13+08:00"

PROGRAMMES_PATH = REAL_ROOT / "programmes.json"
CURRICULA_PATH = REAL_ROOT / "curriculum.json"
COURSES_PATH = REAL_ROOT / "courses.json"
OFFERINGS_PATH = REAL_ROOT / "course_offerings.json"
CATALOGUE_AUDIT_PATH = REAL_ROOT / "course_catalogue_queries.json"
SCHEDULE_AUDIT_PATH = REAL_ROOT / "course_schedule_queries.json"
CALENDAR_PATH = REAL_ROOT / "academic_calendar.md"
POLICY_PATHS = (
    REAL_ROOT / "public_policies" / "registration.md",
    REAL_ROOT / "public_policies" / "exceptions.md",
    REAL_ROOT / "public_policies" / "approval_structure.md",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _metadata(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    match = re.search(r"<!--\s*GEA-METADATA\s*(\{.*?\})\s*-->", raw, re.DOTALL)
    if match is None:
        raise RuntimeError(f"Missing GEA-METADATA block: {path}")
    return json.loads(match.group(1))


def _sha256_json(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _latest_timestamp(*values: str | None) -> str:
    present = [value for value in values if value is not None]
    return max(present, key=lambda value: datetime.fromisoformat(value))


def _source(
    *,
    source_type: str,
    version: str,
    source_url: str | None,
    access_status: str,
    classification: str,
    programme: str | None = None,
    admission_cohort: str | None = None,
    effective_academic_year: str | None = None,
    offering_academic_year: str | None = None,
    origin: str = "VERIFIED_REAL",
    retrieved_at: str | None = MANUAL_RETRIEVED_AT,
    retrieval_method: str | None = "BROWSER_NORMALIZATION",
    content_sha256: str | None = None,
    checksum_scope: str | None = None,
    access_note: str | None = None,
    request_parameters: dict[str, str] | None = None,
) -> dict[str, Any]:
    if access_status in {"AUTHENTICATION_REQUIRED", "UNAVAILABLE"}:
        retrieved_at = None
        retrieval_method = None
        content_sha256 = None
        checksum_scope = None
    return {
        "source_type": source_type,
        "programme": programme,
        "admission_cohort": admission_cohort,
        "effective_academic_year": effective_academic_year,
        "offering_academic_year": offering_academic_year,
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "checked_at": _latest_timestamp(AS_OF, retrieved_at),
        "version": version,
        "origin": origin,
        "access_status": access_status,
        "classification": classification,
        "retrieval_method": retrieval_method,
        "request_parameters": request_parameters or {},
        "content_sha256": content_sha256,
        "checksum_scope": checksum_scope,
        "access_note": access_note,
        "effective_from": None,
        "effective_to": None,
    }


def _curriculum_pdf(
    *,
    programme: str,
    url: str,
    sha256: str,
    version: str = "AY2025-26 curriculum snapshot retrieved 2026-08-31",
    cohort: str | None = "AY2025-26",
    classification: str = "PUBLIC_RESTRICTED",
) -> dict[str, Any]:
    return _source(
        source_type="curriculum",
        programme=programme,
        admission_cohort=cohort,
        effective_academic_year=cohort,
        source_url=url,
        version=version,
        access_status="RETRIEVED",
        classification=classification,
        retrieval_method="DIRECT_PDF_DOWNLOAD",
        content_sha256=sha256,
        checksum_scope="SOURCE_BYTES",
        access_note=(
            "The file was publicly retrievable, but its embedded classification "
            "marking is preserved; raw PDF bytes are not committed."
            if classification == "PUBLIC_RESTRICTED"
            else None
        ),
    )


def _source_catalog(
    catalogue_audit: dict[str, Any], schedule_audit: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Return definitions for every source ID the real-data bundle may cite."""

    catalogue_queries = catalogue_audit.get("queries", [])
    schedule_queries = schedule_audit.get("queries", [])
    catalog: dict[str, dict[str, Any]] = {
        "ntu.ccds.programmes.current": _source(
            source_type="programme_index",
            source_url=(
                "https://www.ntu.edu.sg/computing/admissions/"
                "undergraduate-programmes"
            ),
            version="Current public CCDS undergraduate programme index retrieved 2026-08-31",
            access_status="RETRIEVED",
            classification="PUBLIC",
        ),
        "ntu.course_content.ay2026-27.s1": _source(
            source_type="course_catalogue",
            source_url=catalogue_audit["source_url"],
            version=(
                "Official NTU public course-content response union for AY2026-27 "
                "Semester 1"
            ),
            effective_academic_year="AY2026-27",
            offering_academic_year="AY2026-27",
            access_status="RETRIEVED",
            classification="PUBLIC",
            retrieved_at=catalogue_audit["retrieved_at"],
            retrieval_method="HTTP_POST_QUERY_MATRIX",
            content_sha256=catalogue_audit["normalized_sha256"],
            checksum_scope="NORMALIZED_EXTRACTION",
            request_parameters={
                "acadsem": str(catalogue_audit["academic_period"]),
                "boption": "CLoad",
                "query_count": str(len(catalogue_queries)),
            },
            access_note=(
                "Checksum covers the normalized union, not transient HTML response bytes."
            ),
        ),
        "ntu.class_schedule.ay2026-27.s1": _source(
            source_type="class_schedule",
            source_url=schedule_audit["source_url"],
            version=(
                "Official NTU public class-schedule response union for AY2026-27 "
                "Semester 1"
            ),
            effective_academic_year="AY2026-27",
            offering_academic_year="AY2026-27",
            access_status="RETRIEVED",
            classification="PUBLIC",
            retrieved_at=schedule_audit["retrieved_at"],
            retrieval_method="HTTP_POST_QUERY_MATRIX",
            content_sha256=schedule_audit["normalized_sha256"],
            checksum_scope="NORMALIZED_EXTRACTION",
            request_parameters={
                "acadsem": str(schedule_audit["academic_period"]),
                "boption": "CLoad",
                "query_count": str(len(schedule_queries)),
                "direct_lookup_url": str(schedule_audit.get("direct_source_url", "not-used")),
            },
            access_note=(
                "Checksum covers normalized offerings and indexes, not transient HTML; "
                "the public schedule does not expose total capacity or eligibility."
            ),
        ),
        "ntu.ccds.curriculum.aisc.ay2025-26": _curriculum_pdf(
            programme="AISC",
            url="https://www.ntu.edu.sg/docs/librariesprovider118/ug/aisc/ay2025/ccds_ay25-26_aisc.pdf?sfvrsn=c12c2837_1",
            sha256="8949581619231f5cf6284e5988ca0f549ad69406838448a037923540ee9e6b04",
            version="AY2025-26 AISC curriculum, updated 9 Apr 2026",
        ),
        "ntu.ccds.curriculum.csc.ay2025-26": _curriculum_pdf(
            programme="CSC",
            url="https://www.ntu.edu.sg/media/docs/librariesprovider118/ug/cs/ay2025/ccds_ay25-26_csc.pdf?sfvrsn=54046390_1",
            sha256="461407dad550a205e38e91a2784c99d3cd86e342493c3a0dad8b98567b4dcbd0",
            version="AY2025-26 CSC curriculum, updated 8 Apr 2026",
        ),
        "ntu.ccds.curriculum.ce.ay2025-26": _curriculum_pdf(
            programme="CE",
            url="https://www.ntu.edu.sg/docs/librariesprovider118/ug/ce/ay2025/ccds_ay25-26_ce.pdf?sfvrsn=c36e2a37_1",
            sha256="31e4e1a69c61883f03b97aa461cb5dfee31df867613cf878182e7fceb8d24dbd",
            version="Revised AY2025-26 CE curriculum snapshot retrieved 2026-08-31",
        ),
        "ntu.ccds.curriculum.dsai.ay2025-26": _curriculum_pdf(
            programme="DSAI",
            url="https://www.ntu.edu.sg/docs/librariesprovider118/ug/dsai/ay2025/ccds_ay25-26_dsai.pdf?sfvrsn=a8136852_1",
            sha256="73cd5f1ee33d09ef87d8e89aff44fffe54efa47d463d709cd1de1256ffd72120",
            version="Revised AY2025-26 DSAI curriculum, updated 9 Apr 2026",
        ),
        "ntu.ccds.curriculum.bcg.ay2025-26": _curriculum_pdf(
            programme="BCG",
            url="https://www.ntu.edu.sg/docs/librariesprovider118/ug/bcg/ccds_ay25-26_bcg.pdf?sfvrsn=e031cdd8_1",
            sha256="acb73e935c605110252eaf1d711e32d01b0c9dbe5e5e4d1e7460ca7f4add42ec",
        ),
        "ntu.ccds.curriculum.bce.ay2025-26": _curriculum_pdf(
            programme="BCE",
            url="https://www.ntu.edu.sg/docs/librariesprovider118/ug/bce/ccds_ay25-26_bce.pdf?sfvrsn=1d91f591_1",
            sha256="b383bead7d2b33efc17d9a09e3f7fb609cd364215d31f3d3b5d19283eb392c09",
        ),
        "ntu.ccds.curriculum.csec.ay2025-26": _curriculum_pdf(
            programme="CSEC",
            url="https://www.ntu.edu.sg/docs/librariesprovider118/ug/ddandecons/ay2025/ccds_ay25-26_csec.pdf?sfvrsn=2e87a0ef_1",
            sha256="89e85838cf3065fa5f1601306440221c06f9205644247abd089b2f6ce8af80b9",
        ),
        "ntu.ccds.curriculum.ceec.ay2025-26": _curriculum_pdf(
            programme="CEEC",
            url="https://www.ntu.edu.sg/docs/librariesprovider118/ug/ddandecons/ay2025/ccds_ay25-26_ceec.pdf?sfvrsn=cfdcca4f_1",
            sha256="fd99e1d9f464451beba90d0a37f78dc49a38278f5aff3685d5e15e2668e474ec",
        ),
        "ntu.ccds.curriculum.csc-ent.ay2025-26": _curriculum_pdf(
            programme="CSC-ENT",
            url="https://www.ntu.edu.sg/docs/librariesprovider118/ug/doublemajorincecsandbusiness/csc/ccds_ay25-26_csc_ent.pdf?sfvrsn=d2a4b831_1",
            sha256="ab4d33932809df50b98a467fe44e2e72e3bc1143206a8cfdde4755107cc59cb3",
        ),
        "ntu.ccds.curriculum.csc-business.ay2025-26": _curriculum_pdf(
            programme="CSC",
            url="https://www.ntu.edu.sg/docs/librariesprovider118/ug/doublemajorincecsandbusiness/csc/ccds_ay25-26_csc_2bm.pdf?sfvrsn=444c41de_1",
            sha256="0dd445065df5853f46f9afd7d5dd34a1d836c93f2ca8ef7ee0b2352c9810eb61",
        ),
        "ntu.ccds.curriculum.csc-itp.ay2025-26": _curriculum_pdf(
            programme="CSC-ITP",
            url="https://www.ntu.edu.sg/docs/librariesprovider118/ug/doublemajorincecsandbusiness/csc/ccds_ay25-26_csc_2bm_itp.pdf?sfvrsn=38eff36d_1",
            sha256="d58e9e1b868caa48f34eb916d5562586bd029b3f9b06fa6e73bec00cfb417d87",
        ),
        "ntu.ccds.curriculum.csc-sust.ay2025-26": _curriculum_pdf(
            programme="CSC-SUST",
            url="https://www.ntu.edu.sg/docs/librariesprovider118/ug/doublemajorincecsandbusiness/csc/ccds_ay25-26_csc_sust.pdf?sfvrsn=db586968_1",
            sha256="84924c02aeb3244f0cc9f63d9bba2e003ce704d6fd949aa3d83e4223afbad933",
        ),
        "ntu.ccds.curriculum.ce-dana.ay2025-26.legacy": _curriculum_pdf(
            programme="CE-DANA",
            url="https://www.ntu.edu.sg/docs/librariesprovider118/ug/doublemajorincecsandbusiness/ce/curriculum-structure-2025---computer-engineering--2nd-major-business-%28data-analystics%29.pdf?sfvrsn=659fd8fb_1",
            sha256="3288d8e833a8c8508e1d71dff0fee9249cebdb392097f87ebe270bf046208797",
            version=(
                "Accessible older AY2025-26 CE Data Analytics PDF; retained only as "
                "a documented source conflict"
            ),
        ),
        "ntu.ccds.curriculum.ce-ent.ay2025-26": _curriculum_pdf(
            programme="CE-ENT",
            url="https://www.ntu.edu.sg/docs/librariesprovider118/ug/doublemajorincecsandbusiness/ce/curriculum-structure-2025---computer-engineering--2nd-major-business-%28entrepreneurship%29.pdf?sfvrsn=de09695f_1",
            sha256="20bba0f3ad0bf371188c09c65f4857fdb054dd854c50844e40c7c67224c2b7f8",
        ),
        "ntu.ccds.curriculum.ce-sust.ay2025-26": _curriculum_pdf(
            programme="CE-SUST",
            url="https://www.ntu.edu.sg/docs/librariesprovider118/ug/ce/ay2025/ccds_ay25-26_ce_sust.pdf?sfvrsn=425ffa9d_1",
            sha256="5a24fb4d7eacb4400404bbfab3fb4a1f762c99df6a7e17156fd26a1f22eaf49c",
            version=(
                "AY2025-26 CE Sustainability curriculum; includes a preserved "
                "professional-internship/professional-attachment total conflict"
            ),
        ),
        "ntu.ccds.curriculum.dsai-sust.ay2025-26": _curriculum_pdf(
            programme="DSAI-SUST",
            url="https://www.ntu.edu.sg/docs/librariesprovider118/ug/dsai/ay2025/ccds_ay25-26_dsai_sust.pdf?sfvrsn=5eb7ecd4_1",
            sha256="a0ec275868bdf84e24bca4b7b6d7ba9503f2565e6e2c583443171e289eef8937",
            version="Revised AY2025-26 DSAI Sustainability curriculum snapshot",
        ),
        "ntu.ccds.curriculum.acda.unversioned-pdf": _curriculum_pdf(
            programme="ACDA",
            url="https://www.ntu.edu.sg/media/docs/librariesprovider84/nbs-ug/programme-curriculum/acda.pdf?sfvrsn=e2a160c5_1",
            sha256="b21bec7d23bea8e0e00338f081a920e69b8d9292c06425fc9a1653a0f860be9f",
            version="Unversioned ACDA public curriculum list retrieved 2026-08-31",
            cohort=None,
            classification="PUBLIC",
        ),
        "ntu.ccds.curriculum.bacf.unversioned-pdf": _curriculum_pdf(
            programme="BACF",
            url="https://www.ntu.edu.sg/media/docs/librariesprovider84/nbs-ug/programme-curriculum/bacf.pdf?sfvrsn=2e4131b7_1",
            sha256="10ed8a9a66a498214aec3034909d856692d4b70ac55f3890a750b4b23039b800",
            version="Unversioned BACF public curriculum list retrieved 2026-08-31",
            cohort=None,
            classification="PUBLIC",
        ),
    }
    catalog.update(_non_pdf_sources())
    return catalog


def _non_pdf_sources() -> dict[str, dict[str, Any]]:
    """Public pages, public guidance, and explicit access gaps."""

    return {
        "ntu.ccds.curriculum.ce-bus.ay2025-26.indexed": _source(
            source_type="curriculum_index",
            programme="CE-BUS",
            admission_cohort="AY2025-26",
            effective_academic_year="AY2025-26",
            source_url="https://www.ntu.edu.sg/docs/librariesprovider118/ug/doublemajorincecsandbusiness/ce/curriculum-structure-2025---computer-engineering--2nd-major-business-%28main-stream%29.pdf?sfvrsn=28c58d75_1",
            version="Indexed AY2025-26 CE Business curriculum summary",
            access_status="PARTIALLY_RETRIEVED",
            classification="PUBLIC_RESTRICTED",
            retrieval_method="OFFICIAL_INDEX_NORMALIZATION",
            access_note=(
                "The official index exposed the 146-AU summary, but the PDF returned "
                "HTTP 404 on 2026-08-31; no detailed course plan is asserted."
            ),
        ),
        "ntu.ccds.curriculum.ce-itp.ay2025-26.indexed": _source(
            source_type="curriculum_index",
            programme="CE-ITP",
            admission_cohort="AY2025-26",
            effective_academic_year="AY2025-26",
            source_url="https://www.ntu.edu.sg/docs/librariesprovider118/ug/doublemajorincecsandbusiness/ce/ay2526_computer-engineering-with-a-second-major-in-business-curriculum-%28itp%29.pdf?sfvrsn=deba954a_1",
            version="Indexed AY2025-26 CE Business ITP curriculum summary",
            access_status="PARTIALLY_RETRIEVED",
            classification="PUBLIC_RESTRICTED",
            retrieval_method="OFFICIAL_INDEX_NORMALIZATION",
            access_note=(
                "The official index exposed the 146/147-AU totals, but direct retrieval "
                "was unavailable on 2026-08-31; no detailed course plan is asserted."
            ),
        ),
        "ntu.ccds.curriculum.overview.current": _source(
            source_type="curriculum_index",
            source_url="https://www.ntu.edu.sg/computing/discover-ccds/curriculum",
            version="Current unversioned CCDS curriculum overview retrieved 2026-08-31",
            access_status="RETRIEVED",
            classification="PUBLIC",
            access_note=(
                "This unversioned overview is a structural summary and conflict witness, "
                "not admission-cohort authority."
            ),
        ),
        "ntu.ccds.curriculum.acda.public-page": _source(
            source_type="curriculum",
            programme="ACDA",
            source_url="https://www.ntu.edu.sg/computing/admissions/undergraduate-programmes/detail/double-degree-in-accountancy-and-science",
            version="Unversioned public ACDA programme curriculum page retrieved 2026-08-31",
            access_status="RETRIEVED",
            classification="PUBLIC",
            access_note="The public page states totals but does not identify an admission cohort.",
        ),
        "ntu.ccds.curriculum.bacf.public-page": _source(
            source_type="curriculum",
            programme="BACF",
            source_url="https://www.ntu.edu.sg/education/undergraduate-programme/bachelor-of-applied-computing-in-finance",
            version="Unversioned public BACF programme curriculum page retrieved 2026-08-31",
            access_status="RETRIEVED",
            classification="PUBLIC",
            access_note="The public page states totals but does not identify an admission cohort.",
        ),
        "ntu.ccds.curriculum.ce-dana.ay2025-26.revised-index": _source(
            source_type="curriculum_index",
            programme="CE-DANA",
            admission_cohort="AY2025-26",
            effective_academic_year="AY2025-26",
            source_url="https://www.ntu.edu.sg/docs/librariesprovider118/ug/doublemajorincecsandbusiness/ce/ccds_ay25-26_ce_dana.pdf?sfvrsn=bfe35db0_1",
            version="Indexed revised AY2025-26 CE Data Analytics curriculum as of 8 Apr 2026",
            access_status="PARTIALLY_RETRIEVED",
            classification="PUBLIC_RESTRICTED",
            retrieval_method="OFFICIAL_INDEX_NORMALIZATION",
            access_note=(
                "Official indexed PDF text yielded the 136-AU structure and normalized "
                "48-row plan, but a fresh direct retrieval was unavailable."
            ),
        ),
        "ntu.ccds.curriculum.ecds.ay2025-26": _source(
            source_type="curriculum",
            programme="ECDS",
            admission_cohort="AY2025-26",
            effective_academic_year="AY2025-26",
            source_url="https://www.ntu.edu.sg/education/undergraduate-programme/bachelor-of-science-in-economics-and-data-science",
            version="ECDS public curriculum page for the AY2025-26 intake",
            access_status="RETRIEVED",
            classification="PUBLIC",
        ),
        "ntu.ccds.curriculum.macs.ay2025-26": _source(
            source_type="curriculum",
            programme="MACS",
            admission_cohort="AY2025-26",
            effective_academic_year="AY2025-26",
            source_url="https://www.ntu.edu.sg/spms/about-us/mathematics/undergrad/degree-programmes/macs-%28matric-yr-2025%29",
            version="MACS public curriculum page for Matriculation Year 2025",
            access_status="RETRIEVED",
            classification="PUBLIC",
        ),
        "ntu.ccds.curriculum.btech-comp.2025-public-page": _source(
            source_type="curriculum",
            programme="BTECH-COMP",
            source_url="https://www.ntu.edu.sg/education/undergraduate-programme/bachelor-of-technology-in-computing-skillsfuture-work-study-degree",
            version="Public BTech Computing page and linked 2025 brochure facts",
            access_status="PARTIALLY_RETRIEVED",
            classification="PUBLIC",
            access_note=(
                "The public material describes three stacks but does not publish a "
                "cohort-specific AU total or complete course plan."
            ),
        ),
        "ntu.ccds.curriculum.authenticated-current": _source(
            source_type="curriculum_index",
            source_url="https://entuedu.sharepoint.com/sites/Student/cs/myccds/SitePages/Curriculum-Structure.aspx",
            version="Current CCDS Curriculum Structure target linked by the public registration page",
            access_status="AUTHENTICATION_REQUIRED",
            classification="AUTHENTICATED",
            access_note=(
                "The exact official target requires NTU authentication; no content was "
                "retrieved and no checksum or current-cohort rule is claimed."
            ),
        ),
        "ntu.calendar.ay2026-27": _source(
            source_type="academic_calendar",
            effective_academic_year="AY2026-27",
            offering_academic_year="AY2026-27",
            source_url="https://www.ntu.edu.sg/media/docs/default-source/office-of-academic-services/ntu-academic-calendar-ay2026-27-%28semester%29937cc0af-82d7-495d-b414-ff30dfc48421.pdf?sfvrsn=1c9ce142_1",
            version="AY2026-27 semester calendar, published 19 May 2026",
            access_status="RETRIEVED",
            classification="PUBLIC",
            retrieval_method="DIRECT_PDF_DOWNLOAD",
            content_sha256="ecf21e5034d3edf2ff8b9765a615043942f61b5f23988de649a67492bd415bb1",
            checksum_scope="SOURCE_BYTES",
        ),
        "ntu.academic_activities.undergraduate": _source(
            source_type="academic_schedule",
            source_url="https://www.ntu.edu.sg/media/docs/default-source/office-of-academic-services/schedule-of-key-academic-activities-%28undergraduate-programmes%2901dfb46d-61a0-4b3b-99ce-8dbb4f59fc11.pdf?sfvrsn=df72aad4_1",
            version="Public schedule of key undergraduate academic activities retrieved 2026-08-31",
            access_status="RETRIEVED",
            classification="PUBLIC",
        ),
        "ntu.internship_schedule.ay2026-27": _source(
            source_type="academic_schedule",
            effective_academic_year="AY2026-27",
            offering_academic_year="AY2026-27",
            source_url="https://www.ntu.edu.sg/media/docs/default-source/office-of-academic-services/schedule-for-attachment-and-internship-programmes_ay2026-27-%28confirmed%29.pdf?sfvrsn=eab84d86_1",
            version="Confirmed AY2026-27 attachment and internship schedule dated 25 Dec 2025",
            access_status="RETRIEVED",
            classification="PUBLIC",
        ),
        "ntu.handbook.ay2023-24": _source(
            source_type="academic_handbook",
            admission_cohort="AY2023-24",
            effective_academic_year="AY2023-24",
            source_url="https://www.ntu.edu.sg/docs/default-source/office-of-academic-services/academic-structure-handbook-%28undergraduate-studies%29-ay2023-24.pdf",
            version="Academic Structure Handbook for AY2023-24 admission cohort, updated 15 Jul 2023",
            access_status="RETRIEVED",
            classification="PUBLIC",
        ),
        "ntu.handbook.ay2024-25": _source(
            source_type="academic_handbook",
            admission_cohort="AY2024-25",
            effective_academic_year="AY2024-25",
            source_url="https://www.ntu.edu.sg/docs/default-source/office-of-academic-services/academic-handbook-%28undergraduate-studies%29-ay2024-25_fgo_20240828.pdf?sfvrsn=58dcbeb5_3",
            version="Academic Handbook for AY2024-25 admission cohort, FGO revision 28 Aug 2024",
            access_status="RETRIEVED",
            classification="PUBLIC",
        ),
        "ntu.handbook.ay2025-26": _source(
            source_type="academic_handbook",
            admission_cohort="AY2025-26",
            effective_academic_year="AY2025-26",
            source_url="https://www.ntu.edu.sg/docs/default-source/office-of-academic-services/academic-handbook-%28undergraduate-studies%29-ay2025-26.pdf?sfvrsn=6701e0b3_1",
            version="Academic Handbook for the AY2025-26 admission cohort",
            access_status="RETRIEVED",
            classification="PUBLIC",
        ),
        "ntu.handbook.ay2026-27": _source(
            source_type="academic_handbook",
            admission_cohort="AY2026-27",
            effective_academic_year="AY2026-27",
            source_url="https://www.ntu.edu.sg/media/docs/default-source/office-of-academic-services/academic-handbook-(undergraduate-studies)-ay2026-27v2.pdf?sfvrsn=31d42f33_1",
            version="Academic Handbook for the AY2026-27 admission cohort, updated 31 Jul 2026",
            access_status="RETRIEVED",
            classification="PUBLIC",
        ),
        "ntu.handbook.ay2022-23.unavailable": _source(
            source_type="academic_handbook",
            version="AY2022-23 official-public handbook acquisition gap checked 2026-08-31",
            source_url=None,
            access_status="UNAVAILABLE",
            classification="UNKNOWN",
            origin="UNKNOWN",
            access_note=(
                "No retrievable official-public AY2022-23 undergraduate handbook URL "
                "was established in this collection run."
            ),
        ),
        "ntu.ccds.registration.public": _source(
            source_type="ccds_guidance",
            source_url="https://www.ntu.edu.sg/computing/your-journey/registration",
            version="Current public CCDS course-registration page retrieved 2026-08-31",
            access_status="RETRIEVED",
            classification="PUBLIC",
        ),
        "ntu.registration.guidelines.authenticated-current": _source(
            source_type="registration_guidance",
            source_url="https://entuedu.sharepoint.com/sites/Student/dept/sasd/oas/SitePages/Course%20Registration/main.aspx?cid=1dd32040-8d37-46d9-8296-6d4e57c526a4&csf=1&e=HVbigG&web=1",
            version="Current Course Registration Guidelines target linked by the public CCDS page",
            access_status="AUTHENTICATION_REQUIRED",
            classification="AUTHENTICATED",
            access_note=(
                "The exact official target requires NTU authentication; personalised and "
                "detailed registration content was not retrieved and no checksum is claimed."
            ),
        ),
        "ntu.ccds.student_enquiries": _source(
            source_type="ccds_contacts",
            source_url="https://www.ntu.edu.sg/computing/contact-us/students'-enquiries",
            version="Current public CCDS student-enquiries routing page retrieved 2026-08-31",
            access_status="RETRIEVED",
            classification="PUBLIC",
        ),
        "ntu.ccds.exchange.contacts": _source(
            source_type="ccds_contacts",
            source_url="https://www.ntu.edu.sg/computing/contact-us/exchange-programme-%28students%29",
            version="Current public CCDS exchange-student contacts retrieved 2026-08-31",
            access_status="RETRIEVED",
            classification="PUBLIC",
        ),
        "ntu.ccds.exchange.guidelines.2026-02-27": _source(
            source_type="exception_guidance",
            source_url="https://www.ntu.edu.sg/media/docs/librariesprovider118/ug/ccds-exchange-guidelines_27022026.pdf?sfvrsn=1cafd358_1",
            version="CCDS Exchange Guidelines updated 27 Feb 2026",
            access_status="RETRIEVED",
            classification="PUBLIC",
        ),
        "ntu.ccds.course_exemption": _source(
            source_type="exception_guidance",
            source_url="https://www.ntu.edu.sg/computing/admissions/undergraduate-programmes/course-exemption",
            version="Current public CCDS course-exemption page retrieved 2026-08-31",
            access_status="RETRIEVED",
            classification="PUBLIC",
        ),
        "ntu.icc.faq": _source(
            source_type="exception_guidance",
            source_url="https://www.ntu.edu.sg/education/inspire/interdisciplinary-collaborative-core-%28icc%29/frequently-asked-questions",
            version="Current public ICC FAQ retrieved 2026-08-31",
            access_status="RETRIEVED",
            classification="PUBLIC",
        ),
        "ntu.stars.user_guide.v1": _source(
            source_type="registration_guidance",
            source_url="https://www.ntu.edu.sg/docs/librariesprovider121/undergraduate/current_students/starsplanner_stars_user_guide.pdf?sfvrsn=8ad88f90_2",
            version="Public STARS Planner and STARS user guide v1.0; effective date unspecified",
            access_status="RETRIEVED",
            classification="PUBLIC",
            access_note=(
                "The guide contains legacy GERPE/UE terminology and has no stated current "
                "effective period; it is not generalized to current policy."
            ),
        ),
        "ntu.graduation.matters": _source(
            source_type="ccds_guidance",
            source_url="https://www.ntu.edu.sg/education/academic-services/graduation-matters",
            version="Current public graduation-matters page retrieved 2026-08-31",
            access_status="RETRIEVED",
            classification="PUBLIC",
        ),
        "ntu.matriculation.undergraduate.ay2026-27": _source(
            source_type="registration_guidance",
            effective_academic_year="AY2026-27",
            offering_academic_year="AY2026-27",
            source_url="https://www.ntu.edu.sg/admissions/matriculation",
            version="AY2026-27 undergraduate matriculation and candidature guidance",
            access_status="RETRIEVED",
            classification="PUBLIC",
        ),
        "ntu.ccds.registration.historical.scse": _source(
            source_type="registration_guidance",
            source_url="https://www.ntu.edu.sg/docs/librariesprovider118/ug/course-registration-guide.pdf",
            version="Historical SCSE registration guide with unspecified effective period",
            access_status="PARTIALLY_RETRIEVED",
            classification="PUBLIC",
            access_note=(
                "The guide is retained only as historical/unspecified context and must "
                "not be treated as current CCDS policy."
            ),
        ),
    }


def _base_records(
    programmes: list[dict[str, Any]],
    curricula: list[dict[str, Any]],
    courses: list[dict[str, Any]],
    offering_collection: dict[str, Any],
    calendar: dict[str, Any],
    policies: list[dict[str, Any]],
) -> tuple[dict[str, set[str]], dict[str, list[Any]]]:
    """Collect reverse links and normalized facts before coverage is added."""

    reverse: dict[str, set[str]] = defaultdict(set)
    facts: dict[str, list[Any]] = defaultdict(list)

    def link(source_ids: list[str], record_id: str, fact: Any) -> None:
        for source_id in source_ids:
            reverse[source_id].add(record_id)
            facts[source_id].append({"record_id": record_id, "fact": fact})

    for programme in programmes:
        link(programme.get("source_ids", []), programme["programme_id"], programme)
    for curriculum in curricula:
        link(curriculum.get("source_ids", []), curriculum["curriculum_id"], curriculum)
    for course in courses:
        record_id = f"course.{course['code']}"
        link(course.get("source_ids", []), record_id, course)
        for appearance in course.get("catalogue_appearances", []):
            link(appearance.get("source_ids", []), record_id, appearance)
    collection_sources = offering_collection.get("source_ids", [])
    if collection_sources:
        wrapper_fact = {
            key: value
            for key, value in offering_collection.items()
            if key != "offerings"
        }
        link(collection_sources, "dataset.course_offerings", wrapper_fact)
    for offering in offering_collection.get("offerings", []):
        link(offering.get("source_ids", []), offering["offering_id"], offering)
    link(calendar.get("source_ids", []), calendar["document_id"], calendar)
    for event in calendar.get("events", []):
        link(event.get("source_ids", []), event["event_id"], event)
    for document in policies:
        link(document.get("source_ids", []), document["document_id"], document)
        for section in document.get("sections", []):
            link(section.get("source_ids", []), section["section_id"], section)
    return reverse, facts


def _expected_ids(
    *,
    programmes: list[dict[str, Any]],
    curricula: list[dict[str, Any]],
    courses: list[dict[str, Any]],
    offering_collection: dict[str, Any],
    calendar: dict[str, Any],
    policies: list[dict[str, Any]],
) -> dict[str, list[str]]:
    policy_by_type = {item["document_type"]: item for item in policies}

    def policy_ids(document_type: str) -> list[str]:
        document = policy_by_type[document_type]
        return sorted(
            [
                document["document_id"],
                *(section["section_id"] for section in document.get("sections", [])),
            ]
        )

    return {
        "PROGRAMMES": sorted(item["programme_id"] for item in programmes),
        "CURRICULA": sorted(item["curriculum_id"] for item in curricula),
        "COURSES": sorted(f"course.{item['code']}" for item in courses),
        "COURSE_OFFERINGS": sorted(
            item["offering_id"] for item in offering_collection.get("offerings", [])
        ),
        "ACADEMIC_CALENDAR": sorted(
            [calendar["document_id"], *(item["event_id"] for item in calendar["events"])]
        ),
        "REGISTRATION_GUIDANCE": policy_ids("REGISTRATION"),
        "EXCEPTION_POLICIES": policy_ids("EXCEPTIONS"),
        "APPROVAL_STRUCTURE": policy_ids("APPROVAL_STRUCTURE"),
    }


def _target(
    *,
    target_id: str,
    dataset: str,
    scope_description: str,
    scope_parameters: dict[str, list[str]],
    expected_ids: list[str],
    required_fields: list[str],
    discovery_source_ids: list[str],
    content_status: str,
    gaps: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "target_id": target_id,
        "dataset": dataset,
        "scope_description": scope_description,
        "scope_parameters": scope_parameters,
        "expected_record_count": len(expected_ids),
        "expected_record_ids": expected_ids,
        "inventory_status": "COMPLETE",
        "content_status": content_status,
        "required_fields": required_fields,
        "discovery_source_ids": sorted(set(discovery_source_ids)),
        "gaps": gaps,
    }


def _gap(
    gap_id: str,
    affected_fields: list[str],
    reason: str,
    source_ids: list[str],
    affected_record_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "gap_id": gap_id,
        "dimension": "CONTENT",
        "affected_record_ids": sorted(set(affected_record_ids or [])),
        "affected_fields": affected_fields,
        "reason": reason,
        "source_ids": sorted(set(source_ids)),
    }


def _coverage(
    *,
    programmes: list[dict[str, Any]],
    curricula: list[dict[str, Any]],
    courses: list[dict[str, Any]],
    offering_collection: dict[str, Any],
    catalogue_audit: dict[str, Any],
    schedule_audit: dict[str, Any],
    calendar: dict[str, Any],
    policies: list[dict[str, Any]],
) -> dict[str, Any]:
    ids = _expected_ids(
        programmes=programmes,
        curricula=curricula,
        courses=courses,
        offering_collection=offering_collection,
        calendar=calendar,
        policies=policies,
    )
    programme_sources = sorted(
        {source for item in programmes for source in item.get("source_ids", [])}
    )
    curriculum_sources = sorted(
        {source for item in curricula for source in item.get("source_ids", [])}
    )
    course_sources = sorted(
        {source for item in courses for source in item.get("source_ids", [])}
    )
    offering_sources = sorted(set(offering_collection.get("source_ids", [])))
    calendar_sources = sorted(set(calendar.get("source_ids", [])))
    policy_by_type = {item["document_type"]: item for item in policies}
    partial_curricula = [
        item["curriculum_id"]
        for item in curricula
        if item.get("rules_completeness") != "COMPLETE"
        or item.get("known_gaps")
    ]
    unresolved_codes = catalogue_audit.get("unresolved_supplemental_codes", [])
    unscheduled_codes = schedule_audit.get("direct_unscheduled_codes", [])

    targets = [
        _target(
            target_id="coverage.programmes",
            dataset="PROGRAMMES",
            scope_description=(
                "Every degree or named degree pathway listed on the current public "
                "NTU CCDS undergraduate-programmes index as retrieved on 2026-08-31."
            ),
            scope_parameters={
                "college": ["College of Computing and Data Science"],
                "snapshot_date": ["2026-08-31"],
                "inventory_rule": ["current public admissions index entries"],
            },
            expected_ids=ids["PROGRAMMES"],
            required_fields=[
                "programme_id",
                "code",
                "name",
                "programme_kind",
                "study_mode",
                "ccds_base_programmes",
                "source_ids",
            ],
            discovery_source_ids=programme_sources,
            content_status="COMPLETE",
            gaps=[],
        ),
        _target(
            target_id="coverage.curricula",
            dataset="CURRICULA",
            scope_description=(
                "One grounded curriculum configuration for each current public CCDS "
                "degree/pathway configuration, using the most exact official-public "
                "AY2025-26 or explicitly unversioned source found."
            ),
            scope_parameters={
                "primary_cohort": ["AY2025-26"],
                "college": ["College of Computing and Data Science"],
                "configuration_rule": ["22 programme entries plus CSC Business mainstream"],
            },
            expected_ids=ids["CURRICULA"],
            required_fields=[
                "curriculum_id",
                "programme",
                "configuration_kind",
                "admission_cohort",
                "requirements",
                "rules_completeness",
                "known_gaps",
                "source_ids",
            ],
            discovery_source_ids=[
                *curriculum_sources,
                "ntu.ccds.curriculum.authenticated-current",
            ],
            content_status="PARTIAL",
            gaps=[
                _gap(
                    "gap.curricula.current_and_partial_rules",
                    [
                        "current_ay2026_27_rules",
                        "complete_course_lists",
                        "source_conflict_resolution",
                    ],
                    (
                        "Current AY2026-27 detailed curricula require NTU authentication; "
                        "some public AY2025-26 configurations are unversioned, indexed-only, "
                        "or internally inconsistent. These gaps are recorded per curriculum."
                    ),
                    [
                        *curriculum_sources,
                        "ntu.ccds.curriculum.authenticated-current",
                    ],
                    partial_curricula,
                )
            ],
        ),
        _target(
            target_id="coverage.courses",
            dataset="COURSES",
            scope_description=(
                "Exact deduplicated union returned by the official NTU public AY2026-27 "
                "Semester 1 programme selector matrix, CCDS elective-pool selectors, "
                "and direct lookups for curriculum-plan codes."
            ),
            scope_parameters={
                "academic_period": [str(catalogue_audit["academic_period"])],
                "query_count": [str(len(catalogue_audit.get("queries", [])))],
                "inventory_rule": ["exact successful public response union"],
            },
            expected_ids=ids["COURSES"],
            required_fields=[
                "code",
                "title",
                "aus",
                "prerequisites",
                "exclusions",
                "catalogue_appearances",
                "source_ids",
            ],
            discovery_source_ids=course_sources,
            content_status="PARTIAL",
            gaps=[
                _gap(
                    "gap.courses.unresolved_and_temporal_scope",
                    ["unresolved_curriculum_codes", "semester_2", "historical_versions"],
                    (
                        f"The source is a Semester 1 snapshot; {len(unresolved_codes)} "
                        "curriculum-plan codes returned no public course-content record, "
                        "and Semester 2/historical versions are outside this query scope."
                    ),
                    course_sources,
                )
            ],
        ),
        _target(
            target_id="coverage.course_offerings",
            dataset="COURSE_OFFERINGS",
            scope_description=(
                "Exact normalized offering union returned by the official public "
                "AY2026-27 Semester 1 programme schedule matrix plus direct lookups "
                "for every collected catalogue code."
            ),
            scope_parameters={
                "academic_period": [str(schedule_audit["academic_period"])],
                "query_count": [str(len(schedule_audit.get("queries", [])))],
                "reported_index_count": [str(schedule_audit["index_count"])],
            },
            expected_ids=ids["COURSE_OFFERINGS"],
            required_fields=[
                "offering_id",
                "course_code",
                "academic_year",
                "semester",
                "indexes",
                "observed_programmes",
                "source_ids",
            ],
            discovery_source_ids=offering_sources,
            content_status="PARTIAL",
            gaps=[
                _gap(
                    "gap.offerings.live_registration_state",
                    [
                        "capacity",
                        "vacancies",
                        "waitlist_order",
                        "allocation_priority",
                        "student_eligibility",
                        "unscheduled_courses",
                    ],
                    (
                        "The public schedule supplies timetable/index observations, not "
                        "total capacity, live allocation state, or individual eligibility; "
                        f"{len(unscheduled_codes)} directly queried catalogue codes had no "
                        "conventional timetable row."
                    ),
                    offering_sources,
                )
            ],
        ),
        _target(
            target_id="coverage.academic_calendar",
            dataset="ACADEMIC_CALENDAR",
            scope_description=(
                "AY2026-27 semester calendar and selected public undergraduate activity "
                "windows needed by registration-exception scenarios, including explicit "
                "unknown records where public exact dates are absent."
            ),
            scope_parameters={
                "academic_year": [calendar["academic_year"]],
                "timezone": [calendar["timezone"]],
            },
            expected_ids=ids["ACADEMIC_CALENDAR"],
            required_fields=[
                "document_id",
                "academic_year",
                "events",
                "date_precision",
                "origin",
                "source_ids",
            ],
            discovery_source_ids=calendar_sources,
            content_status="PARTIAL",
            gaps=[
                _gap(
                    "gap.calendar.personalised_and_unpublished_dates",
                    ["personalised_registration_slot", "unpublished_exact_dates"],
                    (
                        "Public calendars do not expose a student's personalised registration "
                        "slot, and any event explicitly marked UNKNOWN remains non-actionable."
                    ),
                    calendar_sources,
                )
            ],
        ),
    ]

    policy_specs = (
        (
            "REGISTRATION",
            "coverage.registration_guidance",
            "REGISTRATION_GUIDANCE",
            [
                "document_id",
                "status",
                "sections",
                "applicability",
                "origin",
                "source_ids",
            ],
            "gap.registration.authenticated_details",
            ["personalised_registration_slot", "detailed_registration_steps", "waitlist_rules"],
            (
                "Personalised times, the detailed authenticated CCDS registration guide, "
                "and deterministic waitlist/allocation rules are not public."
            ),
        ),
        (
            "EXCEPTIONS",
            "coverage.exception_policies",
            "EXCEPTION_POLICIES",
            [
                "document_id",
                "status",
                "sections",
                "applicability",
                "supporting_documents",
                "origin",
                "source_ids",
            ],
            "gap.exceptions.general_workflows",
            [
                "general_late_registration",
                "general_prerequisite_waiver",
                "overload_submission",
                "restricted_repeat_submission",
                "service_level",
            ],
            (
                "Public sources establish narrow cases and eligibility boundaries, but not "
                "a general CCDS late-registration/prerequisite-waiver workflow, complete "
                "evidence set, delegated approver, service time, or guaranteed outcome."
            ),
        ),
        (
            "APPROVAL_STRUCTURE",
            "coverage.approval_structure",
            "APPROVAL_STRUCTURE",
            [
                "document_id",
                "status",
                "sections",
                "routing_role",
                "approval_authority",
                "origin",
                "source_ids",
            ],
            "gap.approvals.general_chain",
            ["general_exception_chain", "delegated_approver", "course_coordinator_authority"],
            (
                "Public contact routing is not proof of final approval authority, and no "
                "general coordinator-to-office-to-approver chain is publicly established."
            ),
        ),
    )
    for document_type, target_id, dataset, fields, gap_id, gap_fields, reason in policy_specs:
        document = policy_by_type[document_type]
        source_ids = sorted(set(document.get("source_ids", [])))
        access_gap_sources = (
            ["ntu.registration.guidelines.authenticated-current"]
            if document_type == "REGISTRATION"
            else []
        )
        targets.append(
            _target(
                target_id=target_id,
                dataset=dataset,
                scope_description=(
                    "All verified and explicitly UNKNOWN sections in the selected official-"
                    "public NTU/CCDS policy corpus as retrieved on 2026-08-31."
                ),
                scope_parameters={
                    "document_id": [document["document_id"]],
                    "snapshot_date": ["2026-08-31"],
                },
                expected_ids=ids[dataset],
                required_fields=fields,
                discovery_source_ids=[*source_ids, *access_gap_sources],
                content_status="PARTIAL",
                gaps=[
                    _gap(
                        gap_id,
                        gap_fields,
                        reason,
                        [*source_ids, *access_gap_sources],
                    )
                ],
            )
        )

    return {
        "contract_id": "coverage.stage2.ntu_ccds.2026-08-31",
        "as_of": _latest_timestamp(
            AS_OF,
            catalogue_audit.get("retrieved_at"),
            schedule_audit.get("retrieved_at"),
        ),
        "scope_description": (
            "Complete official-public inventory for the declared NTU CCDS programme, "
            "curriculum-configuration, AY2026-27 Semester 1 course-query, calendar, and "
            "selected policy corpus scopes; content remains PARTIAL wherever public, "
            "authenticated, temporal, or live-state fields are unavailable."
        ),
        "targets": targets,
    }


def build() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    programmes = _read_json(PROGRAMMES_PATH)
    curricula = _read_json(CURRICULA_PATH)
    courses = _read_json(COURSES_PATH)
    offering_collection = _read_json(OFFERINGS_PATH)
    catalogue_audit = _read_json(CATALOGUE_AUDIT_PATH)
    schedule_audit = _read_json(SCHEDULE_AUDIT_PATH)
    calendar = _metadata(CALENDAR_PATH)
    policies = [_metadata(path) for path in POLICY_PATHS]

    coverage = _coverage(
        programmes=programmes,
        curricula=curricula,
        courses=courses,
        offering_collection=offering_collection,
        catalogue_audit=catalogue_audit,
        schedule_audit=schedule_audit,
        calendar=calendar,
        policies=policies,
    )
    reverse, facts = _base_records(
        programmes,
        curricula,
        courses,
        offering_collection,
        calendar,
        policies,
    )
    for target in coverage["targets"]:
        source_ids = {
            *target["discovery_source_ids"],
            *(source_id for gap in target["gaps"] for source_id in gap["source_ids"]),
        }
        for source_id in source_ids:
            reverse[source_id].add(target["target_id"])

    catalog = _source_catalog(catalogue_audit, schedule_audit)
    unknown = sorted(set(reverse) - set(catalog))
    if unknown:
        raise RuntimeError(
            "Source IDs are referenced but absent from the metadata catalog: "
            + ", ".join(unknown)
        )

    manifest: list[dict[str, Any]] = []
    for source_id in sorted(reverse):
        item = {"source_id": source_id, **catalog[source_id]}
        if item["access_status"] in {"RETRIEVED", "PARTIALLY_RETRIEVED"}:
            if item["content_sha256"] is None:
                source_facts = facts.get(source_id, [])
                if not source_facts:
                    raise RuntimeError(
                        f"Retrieved source {source_id} has no normalized facts to hash"
                    )
                item["content_sha256"] = _sha256_json(source_facts)
                item["checksum_scope"] = "NORMALIZED_EXTRACTION"
        item["dependent_records"] = sorted(reverse[source_id])
        manifest.append(item)

    return manifest, coverage


def main() -> None:
    manifest, coverage = build()
    (REAL_ROOT / "source_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (REAL_ROOT / "coverage.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    counts = {
        target["dataset"]: target["expected_record_count"]
        for target in coverage["targets"]
    }
    print(
        json.dumps(
            {"source_count": len(manifest), "coverage_record_counts": counts},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
