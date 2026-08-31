#!/usr/bin/env python3
"""Make a fair, availability-aware rota for PyData Helsinki organiser roles."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from hashlib import sha256
from itertools import combinations, permutations
import sys

ROLES = ("Coordinator", "MC", "QM")
ROTA_EPOCH = "2026-09"


@dataclass(frozen=True)
class Member:
    name: str
    active_from: str = ROTA_EPOCH
    active_until: str | None = None  # Inclusive; use this instead of deleting.
    unavailable: frozenset[str] = frozenset()

    def is_active(self, month: str) -> bool:
        return self.active_from <= month and (
            self.active_until is None or month <= self.active_until
        )


MEMBERS = (
    Member("Daniel", unavailable=frozenset({"2026-10", "2026-11"})),
    Member("Jouni", unavailable=frozenset({"2026-09"})),
    Member("Niko"),
    Member("Prerna"),
    Member("Teemu"),
    Member("Hugo"),
)
TEAM = tuple(member.name for member in MEMBERS)


def month_key(value: date) -> str:
    """Format a month without platform-dependent strftime behavior."""
    return f"{value.year:04d}-{value.month:02d}"


def parse_month(value: str) -> date:
    """Parse an exact YYYY-MM value as the first day of that month."""
    try:
        parsed = date.fromisoformat(f"{value}-01")
    except ValueError as error:
        raise ValueError(f"invalid month {value!r}; expected YYYY-MM") from error
    if month_key(parsed) != value:
        raise ValueError(f"invalid month {value!r}; expected YYYY-MM")
    return parsed


def validate_members(members: tuple[Member, ...]) -> None:
    names = [member.name for member in members]
    if len(names) != len(set(names)):
        raise ValueError("member names must be unique")
    for member in members:
        if not member.name:
            raise ValueError("member names must not be empty")
        start = parse_month(member.active_from)
        end = parse_month(member.active_until) if member.active_until else None
        if end and end < start:
            raise ValueError(f"{member.name}: active_until is before active_from")
        for month in member.unavailable:
            parse_month(month)


def stable_tie(seed: int, month: str, *values: str) -> bytes:
    """Return a reproducible random-looking tie breaker."""
    text = "|".join((str(seed), month, *values))
    return sha256(text.encode("utf-8")).digest()


def available_names(
    month: str, members: tuple[Member, ...] = MEMBERS
) -> tuple[str, ...]:
    return tuple(
        member.name
        for member in members
        if member.is_active(month) and month not in member.unavailable
    )


def ideal_shift_shares(
    dates: Iterable[date], members: tuple[Member, ...] = MEMBERS
) -> dict[str, Fraction]:
    """Return exact fair shares, counting only months each person is available."""
    validate_members(members)
    shares = {member.name: Fraction() for member in members}
    for event_date in dates:
        month = month_key(event_date)
        available = available_names(month, members)
        if len(available) < len(ROLES):
            raise ValueError(
                f"Only {len(available)} people are available in {month}; "
                f"need {len(ROLES)}."
            )
        for name in available:
            shares[name] += Fraction(len(ROLES), len(available))
    return shares


def make_rota(
    dates: Iterable[date], seed: int | None = None, members: tuple[Member, ...] = MEMBERS
) -> list[tuple[date, dict[str, str]]]:
    """Assign roles using availability and role fair-share credits."""
    dates = sorted(dates)
    if not dates:
        return []
    validate_members(members)
    if month_key(dates[0]) < ROTA_EPOCH:
        raise ValueError(f"the rota starts at {ROTA_EPOCH}")

    seed = 0 if seed is None else seed
    names = tuple(member.name for member in members)
    simulation_dates = monthly_dates(ROTA_EPOCH, month_key(dates[-1]))
    requested_months = {month_key(event_date) for event_date in dates}

    duty_credit = {name: Fraction() for name in names}
    role_credit = {
        name: {role: Fraction() for role in ROLES}
        for name in names
    }
    streak = {name: 0 for name in names}
    last_role = {name: None for name in names}
    rota = []

    for event_date in simulation_dates:
        month = month_key(event_date)
        available = list(available_names(month, members))
        if len(available) < len(ROLES):
            raise ValueError(
                f"Only {len(available)} people are available in {month}; need {len(ROLES)}."
            )

        # Available people earn exactly their ideal share of this month's work.
        for name in available:
            duty_credit[name] += Fraction(len(ROLES), len(available))

        people_options = []
        for people in combinations(available, len(ROLES)):
            selected = set(people)
            new_streak = {
                name: streak[name] + 1 if name in selected else 0
                for name in names
            }
            creates_long_run = max(new_streak.values()) > 2
            fairness_cost = sum(
                (duty_credit[name] - (name in selected)) ** 2
                for name in available
            )
            adjacent_shifts = sum(streak[name] > 0 for name in selected)
            score = (
                fairness_cost,
                creates_long_run,
                max(new_streak.values()),
                adjacent_shifts,
                stable_tie(seed, month, *sorted(people)),
                tuple(sorted(people)),
            )
            people_options.append((score, people, new_streak))

        _, people, streak = min(people_options)
        for name in people:
            duty_credit[name] -= 1

        # Role credit changes only when a person works, so time unavailable
        # cannot alter the role that they are due next.
        for name in people:
            for role in ROLES:
                role_credit[name][role] += Fraction(1, len(ROLES))

        role_options = []
        for role_order in permutations(people):
            assigned_role = dict(zip(role_order, ROLES, strict=True))
            repeated_roles = sum(
                last_role[name] == assigned_role[name] for name in people
            )
            fairness_cost = sum(
                (
                    role_credit[name][role]
                    - (assigned_role[name] == role)
                )
                ** 2
                for name in people
                for role in ROLES
            )
            score = (
                fairness_cost,
                repeated_roles,
                stable_tie(seed, month, *role_order),
                role_order,
            )
            role_options.append((score, role_order))

        _, role_order = min(role_options)
        assignments = dict(zip(ROLES, role_order, strict=True))
        for role, person in assignments.items():
            role_credit[person][role] -= 1
            last_role[person] = role
        if month in requested_months:
            rota.append((event_date, assignments))

    return rota


def monthly_dates(start_month: str, end_month: str) -> list[date]:
    """Return the first day of every month in an inclusive YYYY-MM range."""
    start = parse_month(start_month)
    end = parse_month(end_month)
    if end < start:
        raise ValueError("end month must not be before start month")

    months = []
    current = start
    while current <= end:
        months.append(current)
        year, month = divmod(current.month, 12)
        current = date(current.year + year, month + 1, 1)
    return months


def member_status(
    member: Member, month: str, roles_by_person: dict[str, str]
) -> str:
    """Return a role or a compact status for the team table."""
    if member.name in roles_by_person:
        return roles_by_person[member.name]
    if not member.is_active(month):
        return "(inactive)"
    if month in member.unavailable:
        return "(N/A)"
    return "—"


def summary_rows(
    dates: Iterable[date],
    rota: list[tuple[date, dict[str, str]]],
    members: tuple[Member, ...] = MEMBERS,
) -> list[tuple[str, ...]]:
    """Summarize assignments as counts and shares of available months."""
    assignments_by_month = {
        month_key(event_date): {
            person: role for role, person in assignments.items()
        }
        for event_date, assignments in rota
    }
    rows = []
    for member in members:
        available_months = [
            month_key(event_date)
            for event_date in dates
            if member.is_active(month_key(event_date))
            and month_key(event_date) not in member.unavailable
        ]
        counts = {
            role: sum(
                assignments_by_month[month].get(member.name) == role
                for month in available_months
            )
            for role in ROLES
        }
        no_role = len(available_months) - sum(counts.values())

        def count_and_share(count: int) -> str:
            if not available_months:
                return f"{count} (-)"
            percentage_tenths = (
                count * 1000 + len(available_months) // 2
            ) // len(available_months)
            whole, decimal = divmod(percentage_tenths, 10)
            return f"{count} ({whole}.{decimal}%)"

        rows.append(
            (
                member.name,
                str(len(available_months)),
                *(count_and_share(counts[role]) for role in ROLES),
                count_and_share(no_role),
            )
        )
    return rows


def print_table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> None:
    """Print a padded ASCII table without needing a third-party package."""
    widths = [
        max(len(cell) for cell in column)
        for column in zip(headers, *rows, strict=True)
    ]
    separator = "+" + "+".join("-" * (width + 2) for width in widths) + "+"

    def print_row(row: tuple[str, ...]) -> None:
        cells = " | ".join(
            cell.ljust(width) for cell, width in zip(row, widths, strict=True)
        )
        print(f"| {cells} |")

    print(separator)
    print_row(headers)
    print(separator)
    for row in rows:
        print_row(row)
    print(separator)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "start_month", metavar="START-MONTH", help="first event month (YYYY-MM)"
    )
    parser.add_argument(
        "end_month", metavar="END-MONTH", help="last event month (YYYY-MM)"
    )
    parser.add_argument("--seed", type=int, help="seed for a reproducible random rota")
    args = parser.parse_args()

    try:
        dates = monthly_dates(args.start_month, args.end_month)
        rota = make_rota(dates, args.seed)
    except ValueError as error:
        parser.error(str(error))
    member_by_name = {member.name: member for member in MEMBERS}
    team_rows = []
    role_rows = []
    for event_date, assignments in rota:
        roles_by_person = {person: role for role, person in assignments.items()}
        unavailable = [
            person
            for person in TEAM
            if member_by_name[person].is_active(month_key(event_date))
            and month_key(event_date) in member_by_name[person].unavailable
        ]
        month = month_key(event_date)
        team_rows.append(
            (
                month,
                *(
                    member_status(member_by_name[person], month, roles_by_person)
                    for person in TEAM
                ),
            )
        )
        role_rows.append(
            (
                month,
                *(assignments[role] for role in ROLES),
                ", ".join(unavailable) or "—",
            )
        )

    print("By team member")
    print_table(("Month", *TEAM), team_rows)
    print("\nBy role")
    print_table(("Month", *ROLES, "Unavailable"), role_rows)
    print("\nSummary (unavailable months excluded)")
    print_table(
        ("Person", "Available months", *ROLES, "No role"),
        summary_rows(dates, rota),
    )


if __name__ == "__main__":
    main()
