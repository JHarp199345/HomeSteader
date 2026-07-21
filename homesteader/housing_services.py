"""Program timelines for the Housing Services domain module.

The core keeps documents and ledgers.  This module describes what a *standard*
program timeline expects.  It deliberately keeps event-triggered records such
as due-diligence notes out of scheduled requirements: an honest contact attempt
is important evidence, but its absence is not proof that a file is incomplete.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ScheduledRequirement:
    key: str
    label: str
    event_types: frozenset[str]
    every_months: int
    starts_at_month: int = 0


@dataclass(frozen=True)
class ProgramSchedule:
    key: str
    display_name: str
    duration_months: int
    scheduled_requirements: tuple[ScheduledRequirement, ...]


# This is the first real, inspectable rule—not a hidden assumption.  The
# quarterly income-verification requirement is represented by existing TLS
# fixture/document types.  Other recurring TLS forms can be added only after
# their actual expected schedule is confirmed with program policy.
TLS_STANDARD = ProgramSchedule(
    key="tls",
    display_name="Transitional Living Services",
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


def schedule_for_program(program_name: str | None) -> ProgramSchedule | None:
    """Return a schedule only when the recorded program explicitly identifies it."""
    if program_name and ("tls" in program_name.casefold() or "transitional living services" in program_name.casefold()):
        return TLS_STANDARD
    return None


def add_months(value: date, months: int) -> date:
    """Add whole calendar months without needing a third-party date library."""
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    # Enrollment dates at month-end stay valid in shorter months.
    month_lengths = (31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    return date(year, month, min(value.day, month_lengths[month - 1]))

