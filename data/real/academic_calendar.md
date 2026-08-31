<!-- GEA-METADATA
{
  "document_id": "calendar.ay2026-27",
  "document_type": "ACADEMIC_CALENDAR",
  "title": "NTU undergraduate academic calendar windows used by the prototype",
  "status": "PARTIAL",
  "academic_year": "AY2026-27",
  "timezone": "Asia/Singapore",
  "source_ids": ["ntu.calendar.ay2026-27", "ntu.academic_activities.undergraduate"],
  "events": [
    {
      "event_id": "calendar.s1.teaching",
      "event_type": "TEACHING",
      "name": "Semester 1 teaching span",
      "semester": "SEMESTER_1",
      "start_date": "2026-08-10",
      "end_date": "2026-11-14",
      "date_precision": "EXACT",
      "description": "Published Semester 1 teaching span; the separately recorded recess week interrupts this span.",
      "origin": "VERIFIED_REAL",
      "source_ids": ["ntu.calendar.ay2026-27"]
    },
    {
      "event_id": "calendar.s1.recess",
      "event_type": "RECESS",
      "name": "Semester 1 recess",
      "semester": "SEMESTER_1",
      "start_date": "2026-09-28",
      "end_date": "2026-10-03",
      "date_precision": "EXACT",
      "description": "Published Semester 1 recess week.",
      "origin": "VERIFIED_REAL",
      "source_ids": ["ntu.calendar.ay2026-27"]
    },
    {
      "event_id": "calendar.s2.teaching",
      "event_type": "TEACHING",
      "name": "Semester 2 teaching span",
      "semester": "SEMESTER_2",
      "start_date": "2027-01-11",
      "end_date": "2027-04-17",
      "date_precision": "EXACT",
      "description": "Published Semester 2 teaching span; the separately recorded recess week interrupts this span.",
      "origin": "VERIFIED_REAL",
      "source_ids": ["ntu.calendar.ay2026-27"]
    },
    {
      "event_id": "calendar.s2.recess",
      "event_type": "RECESS",
      "name": "Semester 2 recess",
      "semester": "SEMESTER_2",
      "start_date": "2027-03-01",
      "end_date": "2027-03-06",
      "date_precision": "EXACT",
      "description": "Published Semester 2 recess week.",
      "origin": "VERIFIED_REAL",
      "source_ids": ["ntu.calendar.ay2026-27"]
    },
    {
      "event_id": "calendar.s1.registration.general",
      "event_type": "COURSE_REGISTRATION",
      "name": "General Semester 1 registration period",
      "semester": "SEMESTER_1",
      "start_date": null,
      "end_date": null,
      "date_precision": "GENERAL",
      "description": "The public activity schedule places Semester 1 course registration in mid-to-end June; it does not publish a student's personalised timestamp.",
      "origin": "VERIFIED_REAL",
      "source_ids": ["ntu.academic_activities.undergraduate"]
    },
    {
      "event_id": "calendar.s2.registration.general",
      "event_type": "COURSE_REGISTRATION",
      "name": "General Semester 2 registration period",
      "semester": "SEMESTER_2",
      "start_date": null,
      "end_date": null,
      "date_precision": "GENERAL",
      "description": "The public activity schedule places Semester 2 course registration in December; it does not publish a student's personalised timestamp.",
      "origin": "VERIFIED_REAL",
      "source_ids": ["ntu.academic_activities.undergraduate"]
    },
    {
      "event_id": "calendar.s1.add_drop.general",
      "event_type": "ADD_DROP",
      "name": "General Semester 1 Add/Drop window",
      "semester": "SEMESTER_1",
      "start_date": null,
      "end_date": null,
      "date_precision": "GENERAL",
      "description": "The public activity schedule identifies Teaching Weeks 1 and 2 for full-time undergraduate Add/Drop.",
      "origin": "VERIFIED_REAL",
      "source_ids": ["ntu.academic_activities.undergraduate"]
    },
    {
      "event_id": "calendar.s2.add_drop.general",
      "event_type": "ADD_DROP",
      "name": "General Semester 2 Add/Drop window",
      "semester": "SEMESTER_2",
      "start_date": null,
      "end_date": null,
      "date_precision": "GENERAL",
      "description": "The public activity schedule identifies Teaching Weeks 1 and 2 for full-time undergraduate Add/Drop.",
      "origin": "VERIFIED_REAL",
      "source_ids": ["ntu.academic_activities.undergraduate"]
    },
    {
      "event_id": "calendar.personalised.registration.exact",
      "event_type": "COURSE_REGISTRATION",
      "name": "Exact personalised CCDS registration timestamp",
      "semester": null,
      "start_date": null,
      "end_date": null,
      "date_precision": "UNKNOWN",
      "description": "UNKNOWN: exact personalised registration dates and times are not present in the collected public sources.",
      "origin": "UNKNOWN",
      "source_ids": []
    }
  ],
  "placeholder_reason": null
}
-->

# AY2026–27 academic calendar

This prototype stores only the windows needed to reason about course-registration cases. Exact teaching and recess dates come from the official NTU semester calendar. General registration and Add/Drop timing comes from the official undergraduate key-activities schedule.

The public sources do not expose each student's personalised registration timestamp. That value is explicitly `UNKNOWN`; a later simulator may supply case state but must not relabel it as an official source fact.

All published calendar dates remain subject to change by NTU. Consumers should use the source manifest and retrieval timestamp before relying on this snapshot.
