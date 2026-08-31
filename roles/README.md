# Organiser rota

Create one event per month, including the start and end months:

```sh
uv run roles/roles.py --seed 42 2026-09 2027-12
```

Keep the same seed so the rota stays reproducible. The seed does not use
Python's built-in random or hash functions. It uses SHA-256, exact fractions,
integer percentage rounding, UTF-8, and fixed line endings. With the same
code, inputs, and seed, the table is byte-for-byte identical across Python
versions and operating systems.

The command prints three ASCII tables: assignments by team member, assignments
by role, and a summary. In the team table, an em dash (`—`) means no role and
`(N/A)` means unavailable.

## How fairness works

- Three available people work each month. Other available people get no role.
  Unavailable and inactive people are labelled separately.
- If `A` people are available, each person's fair share is `3/A` shifts and
  `1/A` of each role.
- An unavailable person earns no shift credit. Missed shifts are not saved or
  added later.
- Role credit changes only when a person works. Being unavailable does not
  change their role balance.
- The algorithm balances shift and role credits over time. If choices are
  equally fair, it prefers wider spacing and fewer repeated roles.
- Each month has exactly
  `active organisers - unavailable organisers - 3` no-role em dashes.

An absence must affect the remaining people's chance that month. For example,
with five available people each shift chance is `3/5`; with four it is `3/4`.
In this credit-based algorithm, it can also change later assignments because
the people who covered that month now have different credits. It does not
create catch-up work for the absent person or rewrite earlier months.

This is an online algorithm: it makes each month final so later membership
changes cannot rewrite it. That stability means it cannot also promise the
globally best spacing, shift totals, or role totals for every possible future
availability pattern. Credits keep improving the balance over time. Fairness
is the first priority; spacing is a tie-breaker. The summary table shows the
actual counts and shares for the requested period.

Run the tests with:

```sh
python3 -m unittest discover
```

## Why not a rotating list?

A rotating list handles absence badly. Saving a missed turn creates catch-up
work. Dropping it moves the shared pointer and changes later turns for other
people. Adding or removing a name also changes the list positions.

This script keeps separate credits for each person instead. It counts only
months when they can work.

## Change the team

Edit `MEMBERS` in `roles.py`.

Add a member with the month they join:

```python
Member("New member", active_from="2028-01")
```

For unavailable months:

```python
Member("New member", unavailable=frozenset({"2028-07"}))
```

To remove someone, keep the record and set their last active month. This keeps
old rota results stable:

```python
Member("Former member", active_until="2028-06")
```

A membership change affects the fair shares from its effective month onward;
it cannot change earlier assignments. At least three people must be available
in every month.
