from collections import Counter
from dataclasses import replace
from fractions import Fraction
import os
import subprocess
import sys
import unittest

from roles import roles as rota


DATES = rota.monthly_dates("2026-09", "2027-08")
MEMBERS = tuple(rota.Member(name) for name in "ABCDEF")


class RolesTests(unittest.TestCase):
    def test_equal_team_has_equal_shift_and_role_totals(self) -> None:
        schedule = rota.make_rota(DATES, seed=42, members=MEMBERS)
        self.assertEqual(
            rota.ideal_shift_shares(DATES, MEMBERS),
            {member.name: Fraction(6) for member in MEMBERS},
        )
        self.assertEqual(shift_totals(schedule, MEMBERS), (6, 6, 6, 6, 6, 6))
        self.assert_role_totals_are_balanced(schedule)

    def test_role_totals_stay_balanced_across_seeds(self) -> None:
        for seed in range(25):
            with self.subTest(seed=seed):
                self.assert_role_totals_are_balanced(
                    rota.make_rota(DATES, seed, members=MEMBERS)
                )

    def test_arbitrary_availability_fairness_regression(self) -> None:
        dates = rota.monthly_dates("2026-09", "2027-04")
        available = [
            set(value)
            for value in (
                "BCD", "ACD", "ABCDE", "ABC", "ABDE", "ACDE", "ABC", "BCDE"
            )
        ]
        months = [rota.month_key(day) for day in dates]
        members = tuple(
            rota.Member(
                name,
                unavailable=frozenset(
                    month
                    for month, available_that_month in zip(months, available)
                    if name not in available_that_month
                ),
            )
            for name in "ABCDE"
        )
        schedule = rota.make_rota(dates, seed=42, members=members)
        counts = Counter(name for _, row in schedule for name in row.values())
        self.assertEqual(tuple(counts[name] for name in "ABCDE"), (5, 5, 6, 5, 3))

    def test_querying_a_suffix_does_not_restart_credits(self) -> None:
        full = rota.make_rota(DATES, seed=42, members=MEMBERS)
        later = rota.make_rota(
            rota.monthly_dates("2027-01", "2027-08"),
            seed=42,
            members=MEMBERS,
        )
        self.assertEqual(full[4:], later)

    def test_membership_change_does_not_rewrite_earlier_months(self) -> None:
        original = rota.make_rota(DATES, seed=42, members=MEMBERS)
        joined = (*MEMBERS, rota.Member("G", active_from="2027-03"))
        departed = tuple(
            replace(member, active_until="2027-02")
            if member.name == "F"
            else member
            for member in MEMBERS
        )
        self.assertEqual(
            original[:6], rota.make_rota(DATES, seed=42, members=joined)[:6]
        )
        self.assertEqual(
            original[:6], rota.make_rota(DATES, seed=42, members=departed)[:6]
        )

    def test_no_role_status_matches_the_documented_formula(self) -> None:
        members = (
            rota.Member("A"),
            rota.Member("B"),
            rota.Member("C"),
            rota.Member("D", unavailable=frozenset({"2026-09"})),
            rota.Member("E", active_from="2026-10"),
        )
        dates = rota.monthly_dates("2026-09", "2026-10")
        schedule = rota.make_rota(dates, seed=42, members=members)
        for event_date, assignments in schedule:
            month = rota.month_key(event_date)
            statuses = statuses_for((event_date, assignments), members)
            active = sum(member.is_active(month) for member in members)
            unavailable = sum(
                member.is_active(month) and month in member.unavailable
                for member in members
            )
            self.assertEqual(statuses.count("—"), active - unavailable - 3)
        self.assertIn("(N/A)", statuses_for(schedule[0], members))
        self.assertIn("(inactive)", statuses_for(schedule[0], members))

    def test_summary_uses_available_months_as_denominator(self) -> None:
        members = (
            rota.Member("A", unavailable=frozenset({"2026-09"})),
            *MEMBERS[1:],
        )
        schedule = rota.make_rota(DATES, seed=42, members=members)
        rows = {row[0]: row[1:] for row in rota.summary_rows(DATES, schedule, members)}
        self.assertEqual(rows["A"][0], "11")
        self.assertEqual(rows["B"][0], "12")
        for row in rows.values():
            available_months = int(row[0])
            counts = [int(cell.split()[0]) for cell in row[1:]]
            self.assertEqual(sum(counts), available_months)

    def test_seed_is_reproducible(self) -> None:
        self.assertEqual(
            rota.make_rota(DATES, seed=42, members=MEMBERS),
            rota.make_rota(DATES, seed=42, members=MEMBERS),
        )
        self.assertNotEqual(
            rota.make_rota(DATES, seed=42, members=MEMBERS),
            rota.make_rota(DATES, seed=43, members=MEMBERS),
        )

    def test_cli_output_ignores_python_hash_seed(self) -> None:
        command = [
            sys.executable,
            "roles/roles.py",
            "--seed",
            "42",
            "2026-09",
            "2027-02",
        ]
        outputs = []
        for hash_seed in ("1", "987654321", "random"):
            environment = os.environ.copy()
            environment["PYTHONHASHSEED"] = hash_seed
            outputs.append(subprocess.check_output(command, env=environment))
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0], outputs[2])

    def test_tie_breaker_has_a_stable_digest(self) -> None:
        self.assertEqual(
            rota.stable_tie(42, "2026-09", "A", "B").hex(),
            "41f3e9c336079bd53bb553cd8125f7d3dd63434a27460c742c7e596e463babcf",
        )

    def test_member_configuration_is_validated(self) -> None:
        cases = (
            (rota.Member("A"), rota.Member("A")),
            (rota.Member("A", active_from="2026-9"),),
            (rota.Member("A", active_from="2027-01", active_until="2026-12"),),
            (rota.Member("A", unavailable=frozenset({"later"})),),
        )
        for members in cases:
            with self.subTest(members=members), self.assertRaises(ValueError):
                rota.make_rota([DATES[0]], members=members)

    def test_invalid_ranges_and_too_few_people_fail_cleanly(self) -> None:
        for start, end in (("2026-9", "2027-01"), ("2027-02", "2027-01")):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                rota.monthly_dates(start, end)
        with self.assertRaisesRegex(ValueError, "Only 2 people"):
            rota.make_rota(
                [DATES[0]], members=(rota.Member("A"), rota.Member("B"))
            )

        result = subprocess.run(
            [sys.executable, "roles/roles.py", "2026-01", "2026-02"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def assert_role_totals_are_balanced(
        self, schedule: list[tuple[object, dict[str, str]]]
    ) -> None:
        role_counts: dict[str, Counter[str]] = {}
        for _, assignments in schedule:
            for role, name in assignments.items():
                role_counts.setdefault(name, Counter())[role] += 1
        for name, counts_by_role in role_counts.items():
            counts = [counts_by_role[role] for role in rota.ROLES]
            self.assertLessEqual(
                max(counts) - min(counts), 1, f"unbalanced roles for {name}"
            )


def shift_totals(
    schedule: list[tuple[object, dict[str, str]]], members: tuple[rota.Member, ...]
) -> tuple[int, ...]:
    counts = Counter(name for _, row in schedule for name in row.values())
    return tuple(counts[member.name] for member in members)


def statuses_for(
    entry: tuple[object, dict[str, str]], members: tuple[rota.Member, ...]
) -> list[str]:
    event_date, assignments = entry
    month = rota.month_key(event_date)
    roles_by_person = {person: role for role, person in assignments.items()}
    return [rota.member_status(member, month, roles_by_person) for member in members]


if __name__ == "__main__":
    unittest.main()
