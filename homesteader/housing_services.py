"""Program timelines for the Housing Services domain module.

The core keeps documents and ledgers.  This module describes what a *standard*
program timeline expects.  It deliberately keeps event-triggered records such
as due-diligence notes out of scheduled requirements: an honest contact attempt
is important evidence, but its absence is not proof that a file is incomplete.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path


@dataclass(frozen=True)
class ScheduledRequirement:
    key: str
    label: str
    event_types: frozenset[str]
    every_months: int
    starts_at_month: int = 0
    grace_days: int = 0


@dataclass(frozen=True)
class ProgramSchedule:
    key: str
    display_name: str
    match_terms: tuple[str, ...]
    duration_months: int
    scheduled_requirements: tuple[ScheduledRequirement, ...]


# This is the first real, inspectable rule—not a hidden assumption.  The
# quarterly income-verification requirement is represented by existing TLS
# fixture/document types.  Other recurring TLS forms can be added only after
# their actual expected schedule is confirmed with program policy.
TLS_STANDARD = ProgramSchedule(
    key="tls",
    display_name="Transitional Living Services",
    match_terms=("tls", "transitional living services"),
    duration_months=24,
    scheduled_requirements=(
        ScheduledRequirement(
            key="income_verification",
            label="income eligibility / verification",
            event_types=frozenset({"income_verification_recorded", "income_declaration_recorded"}),
            every_months=3,
        ),
    ),
)

DEFAULT_PROGRAM_SCHEDULES = (TLS_STANDARD,)


def program_schedules_to_dict(schedules: tuple[ProgramSchedule, ...] = DEFAULT_PROGRAM_SCHEDULES) -> dict:
    return {"programs": [
        {
            "key": schedule.key, "display_name": schedule.display_name,
            "match_terms": list(schedule.match_terms), "duration_months": schedule.duration_months,
            "scheduled_requirements": [
                {"key": requirement.key, "label": requirement.label,
                 "event_types": sorted(requirement.event_types), "every_months": requirement.every_months,
                 "starts_at_month": requirement.starts_at_month, "grace_days": requirement.grace_days}
                for requirement in schedule.scheduled_requirements
            ],
        }
        for schedule in schedules
    ]}


def load_program_schedules(path: Path | None = None) -> tuple[ProgramSchedule, ...]:
    """Load a user-controlled local rules file, falling back to safe defaults."""
    if not path or not path.exists():
        return DEFAULT_PROGRAM_SCHEDULES
    payload = json.loads(path.read_text())
    schedules = []
    for item in payload.get("programs", []):
        requirements = tuple(
            ScheduledRequirement(
                key=requirement["key"], label=requirement["label"],
                event_types=frozenset(requirement["event_types"]), every_months=int(requirement["every_months"]),
                starts_at_month=int(requirement.get("starts_at_month", 0)), grace_days=int(requirement.get("grace_days", 0)),
            )
            for requirement in item.get("scheduled_requirements", [])
        )
        schedules.append(ProgramSchedule(
            key=item["key"], display_name=item["display_name"],
            match_terms=tuple(item.get("match_terms", [])), duration_months=int(item["duration_months"]),
            scheduled_requirements=requirements,
        ))
    return tuple(schedules)


def write_default_program_schedules(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(program_schedules_to_dict(), indent=2) + "\n")


def schedule_for_program(program_name: str | None, schedules: tuple[ProgramSchedule, ...] = DEFAULT_PROGRAM_SCHEDULES) -> ProgramSchedule | None:
    """Return a schedule only when the recorded program explicitly identifies it."""
    if not program_name:
        return None
    normalized = program_name.casefold()
    for schedule in schedules:
        if any(term.casefold() in normalized for term in schedule.match_terms):
            return schedule
    return None


def add_months(value: date, months: int) -> date:
    """Add whole calendar months without needing a third-party date library."""
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    # Enrollment dates at month-end stay valid in shorter months.
    month_lengths = (31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    return date(year, month, min(value.day, month_lengths[month - 1]))
