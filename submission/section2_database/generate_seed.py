"""Generate the committed seed SQL for the Section 2 database.

This script is a *build-time* tool, not a runtime dependency. It reads the
Section 1 pipeline output and writes ``ddl/02_seed_members.sql``,
``ddl/03_seed_items.sql`` and ``ddl/04_seed_transactions.sql``, which are
committed to the repository. The database itself stands up from Docker alone --
nothing here runs against a live container.

It exists for two reasons: to make the seed reproducible (so a reviewer can
regenerate it and diff), and to make the Section 1 -> Section 2 linkage explicit
rather than a claim in a README.

Standard library only. Reading fifty rows of CSV and emitting SQL text does not
justify a dataframe dependency, so this section has no ``requirements.txt``.

Usage::

    python generate_seed.py                 # newest Section 1 output
    python generate_seed.py --section1-output path/to/successful_applications_x.csv
    python generate_seed.py --self-check    # run the built-in assertions

Assumptions that are *interpretations* of the brief rather than literal readings
are marked ``ASSUMPTION`` below and repeated in the section README.
"""

from __future__ import annotations

import argparse
import csv
import logging
import random
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final, Iterable, Sequence

logger = logging.getLogger("generate_seed")

SCRIPT_DIR: Final[Path] = Path(__file__).resolve().parent

#: Where Section 1 drops its successful applications.
DEFAULT_SECTION1_DIR: Final[Path] = (
    SCRIPT_DIR.parent / "section1_data_pipeline" / "output" / "successful"
)
DEFAULT_SECTION1_GLOB: Final[str] = "successful_applications_*.csv"

DEFAULT_OUTPUT_DIR: Final[Path] = SCRIPT_DIR / "ddl"


# ---------------------------------------------------------------------------
# Seed parameters
# ---------------------------------------------------------------------------

#: ASSUMPTION: "the first 50 members of a processed dataset from Section 1" is
#: read as the first 50 *rows in file order*. Section 1 writes rows in the order
#: it read them, so this is stable for a given input.
MEMBER_LIMIT: Final[int] = 50

#: Fixed so the generated SQL is byte-identical on every run. Without this the
#: committed files would churn on each regeneration and a diff would be useless.
RANDOM_SEED: Final[int] = 20260918

TRANSACTION_COUNT: Final[int] = 150
WINDOW_DAYS: Final[int] = 90
BASKET_MIN_ITEMS: Final[int] = 1
BASKET_MAX_ITEMS: Final[int] = 5
QUANTITY_MIN: Final[int] = 1
QUANTITY_MAX: Final[int] = 3

#: The item catalogue: (item_name, manufacturer_name, cost, weight_kg, popularity).
#:
#: ``popularity`` is a relative draw weight, not a stored column -- it only
#: shapes the synthetic baskets. It is deliberately skewed so
#: queries/top3_items_by_frequency.sql has an unambiguous answer: the top three
#: weights (40 / 34 / 28) sit well clear of the fourth (16), which at ~450 line
#: items puts roughly 20 purchases between third and fourth place. A flat
#: distribution would make the "top 3" a coin toss between near-ties.
CATALOGUE: Final[tuple[tuple[str, str, float, float, int], ...]] = (
    ("Wireless Earbuds",      "Aurora Audio",        89.90,   0.058, 40),
    ("Over-Ear Headphones",   "Aurora Audio",       219.00,   0.295,  8),
    ("Portable Speaker",      "Aurora Audio",        64.50,   0.560, 12),
    ("Soundbar",              "Aurora Audio",       349.00,   2.850,  3),
    ("Ceramic Mug Set",       "Basalt Home",         24.90,   1.420, 14),
    ("Linen Bedsheet Set",    "Basalt Home",        129.00,   1.850,  6),
    ("Scented Candle",        "Basalt Home",         18.50,   0.340, 34),
    ("Storage Basket",        "Basalt Home",         32.00,   0.780,  9),
    ("Trail Backpack",        "Cindermill Outdoors", 149.00,  1.120,  5),
    ("Insulated Bottle",      "Cindermill Outdoors",  38.90,  0.395, 28),
    ("Camping Lantern",       "Cindermill Outdoors",  45.00,  0.480,  7),
    ("Two-Person Tent",       "Cindermill Outdoors", 289.00,  3.400,  2),
    ("Fitness Tracker",       "Delta Peak",          159.00,  0.042, 11),
    ("Yoga Mat",              "Delta Peak",           54.00,  1.250, 13),
    ("Resistance Band Set",   "Delta Peak",           29.90,  0.620, 15),
    ("Adjustable Dumbbell",   "Delta Peak",          199.00, 12.500,  2),
    ("Chef Knife",            "Everly Kitchen",       89.00,  0.240, 10),
    ("Cast Iron Skillet",     "Everly Kitchen",       74.50,  2.950,  8),
    ("Espresso Grinder",      "Everly Kitchen",      179.00,  1.680,  4),
    ("Silicone Spatula Set",  "Everly Kitchen",       16.90,  0.180, 16),
)

GENERATED_BANNER: Final[str] = (
    "-- ===========================================================================\n"
    "-- GENERATED FILE -- do not edit by hand.\n"
    "--\n"
    "--   Regenerate with:  python generate_seed.py\n"
    "--\n"
    "-- {description}\n"
    "-- Source: {source}\n"
    "-- ===========================================================================\n"
)


# ---------------------------------------------------------------------------
# SQL literal helpers
# ---------------------------------------------------------------------------


def sql_str(value: str) -> str:
    """Render ``value`` as a single-quoted SQL string literal.

    Doubles embedded single quotes, which is the only escape a standard SQL
    string literal needs. The first-50 sample contains no apostrophes, but
    ``O'Brien`` is an ordinary surname and a seed generator that breaks on one
    is a bug waiting for a different input file.
    """
    return "'" + value.replace("'", "''") + "'"


def sql_bool(value: str) -> str:
    """Render Section 1's ``true``/``false`` text as a SQL boolean literal.

    Anything the pipeline did not write as exactly ``true`` is a contract
    violation, not a value to coerce, so this raises rather than guessing.
    """
    normalised = value.strip().lower()
    if normalised not in {"true", "false"}:
        raise ValueError(f"expected 'true' or 'false' for above_18, got {value!r}")
    return normalised


# ---------------------------------------------------------------------------
# Section 1 input
# ---------------------------------------------------------------------------


def find_latest_section1_output(directory: Path) -> Path:
    """Return the most recent ``successful_applications_*.csv`` in ``directory``.

    Chosen by filename rather than mtime: Section 1 stamps every run into the
    name, so the name is the authoritative ordering and survives a git checkout
    (which rewrites mtimes).
    """
    candidates = sorted(directory.glob(DEFAULT_SECTION1_GLOB))
    if not candidates:
        raise FileNotFoundError(
            f"No {DEFAULT_SECTION1_GLOB} found in {directory}. "
            "Run the Section 1 pipeline first, or pass --section1-output."
        )
    latest = candidates[-1]
    logger.info("Using Section 1 output: %s", latest)
    return latest


def reference_datetime(source: Path) -> datetime:
    """Anchor the synthetic transaction window to the Section 1 run timestamp.

    ASSUMPTION: transaction timestamps are synthetic -- the brief supplies no
    sales data -- and are anchored to the ``YYYYMMDD_HHMMSS`` stamp in the
    Section 1 filename rather than to ``now()``. Using the wall clock would make
    the committed SQL churn on every regeneration; anchoring to the input means
    the window only moves when the upstream data actually does.

    ASSUMPTION: that stamp is treated as UTC. Section 1 writes local time, but
    nothing downstream depends on the offset being right -- only on it being
    fixed.
    """
    match = re.search(r"(\d{8}_\d{6})", source.name)
    if not match:
        raise ValueError(
            f"Cannot read a run timestamp from {source.name!r}; pass --reference-date."
        )
    return datetime.strptime(match.group(1), "%Y%m%d_%H%M%S")


def read_members(source: Path, limit: int) -> list[dict[str, str]]:
    """Read the first ``limit`` rows, de-duplicating on ``membership_id``.

    ASSUMPTION: de-duplication drops the later row and does **not** reach further
    down the file to top the count back up to ``limit``. "The first 50 members"
    means the first 50 rows; quietly substituting row 51 would change which
    members are in the database and make the seed depend on collision luck.

    Section 1 documents that ``membership_id`` is only unique per
    ``(last_name, birthday)`` -- see its README, "Membership IDs are not
    guaranteed unique". The sample collides once (``Williamson_2b72a``) at
    roughly row 450, so this branch does not fire on the current input. It is a
    guard against a future Section 1 run whose ordering differs, not a
    workaround for today's data.
    """
    with source.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))[:limit]

    members: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        membership_id = row["membership_id"]
        if membership_id in seen:
            logger.warning(
                "Duplicate membership_id %r in the first %d rows; skipping the later row "
                "(%s %s). The members primary key cannot accept both.",
                membership_id,
                limit,
                row["first_name"],
                row["last_name"],
            )
            continue
        seen.add(membership_id)
        members.append(row)

    logger.info("Read %d member(s) from the first %d row(s)", len(members), len(rows))
    return members


# ---------------------------------------------------------------------------
# Seed file builders
# ---------------------------------------------------------------------------


def build_members_sql(members: Sequence[dict[str, str]], source: Path) -> str:
    """Render ``02_seed_members.sql``: one multi-row INSERT.

    ``birthday`` arrives as a ``YYYYMMDD`` string and is parsed here so a
    malformed value fails at generation time with a clear traceback, rather than
    at container start where it would surface as an opaque initdb failure.
    """
    values = []
    for row in members:
        birthday = datetime.strptime(row["birthday"], "%Y%m%d").date().isoformat()
        values.append(
            "    ({id}, {first}, {last}, {email}, {birthday}, {above_18}, {mobile})".format(
                id=sql_str(row["membership_id"]),
                first=sql_str(row["first_name"]),
                last=sql_str(row["last_name"]),
                email=sql_str(row["email"]),
                birthday=sql_str(birthday),
                above_18=sql_bool(row["above_18"]),
                mobile=sql_str(row["mobile"]),
            )
        )

    return (
        GENERATED_BANNER.format(
            description=f"The first {MEMBER_LIMIT} members of the Section 1 successful output.",
            source=source.name,
        )
        + "\nBEGIN;\n\n"
        + "INSERT INTO members\n"
        + "    (membership_id, first_name, last_name, email, birthday, above_18, mobile)\n"
        + "VALUES\n"
        + ",\n".join(values)
        + ";\n\nCOMMIT;\n"
    )


def build_items_sql(source: Path) -> str:
    """Render ``03_seed_items.sql``: the catalogue, with explicit ``item_id``s.

    ``OVERRIDING SYSTEM VALUE`` is needed because ``item_id`` is
    ``GENERATED ALWAYS AS IDENTITY``. Explicit IDs are worth that keyword: they
    let ``04_seed_transactions.sql`` reference items as plain integers instead of
    burying a correlated subquery in every one of ~450 line items, which keeps
    the seed reviewable. The sequence is fast-forwarded afterwards so the next
    real INSERT does not collide.
    """
    values = [
        "    ({item_id:>2}, {name}, {manufacturer}, {cost}, {weight})".format(
            item_id=index,
            name=sql_str(name),
            manufacturer=sql_str(manufacturer),
            cost=f"{cost:.2f}",
            weight=f"{weight:.3f}",
        )
        for index, (name, manufacturer, cost, weight, _popularity) in enumerate(CATALOGUE, start=1)
    ]

    return (
        GENERATED_BANNER.format(
            description=(
                f"Product catalogue: {len(CATALOGUE)} items across "
                f"{len({m for _, m, *_ in CATALOGUE})} manufacturers."
            ),
            source="CATALOGUE in generate_seed.py",
        )
        + "\nBEGIN;\n\n"
        + "INSERT INTO items (item_id, item_name, manufacturer_name, cost, weight_kg)\n"
        + "OVERRIDING SYSTEM VALUE\n"
        + "VALUES\n"
        + ",\n".join(values)
        + ";\n\n"
        + "-- Fast-forward the identity sequence past the explicit IDs above.\n"
        + "SELECT setval(pg_get_serial_sequence('items', 'item_id'),\n"
        + "              (SELECT MAX(item_id) FROM items));\n\n"
        + "COMMIT;\n"
    )


def weighted_sample(
    rng: random.Random,
    population: Sequence[int],
    weights: Sequence[int],
    k: int,
) -> list[int]:
    """Draw ``k`` *distinct* indices from ``population``, respecting ``weights``.

    ``random.sample`` is uniform and ``random.choices`` draws with replacement,
    so neither does weighted-without-replacement on its own.

    ponytail: rejection loop rather than the textbook weighted reservoir. It is
    three lines instead of fifteen and the retry cost only bites when k
    approaches len(population). Here k <= 5 against a 20-item catalogue, so the
    expected number of retries is under one per basket. If the catalogue ever
    shrinks toward the basket size, swap in an exponential-jump reservoir.
    """
    if k > len(population):
        raise ValueError(f"cannot draw {k} distinct items from {len(population)}")

    drawn: list[int] = []
    while len(drawn) < k:
        (pick,) = rng.choices(population, weights=weights, k=1)
        if pick not in drawn:
            drawn.append(pick)
    return drawn


def build_transactions_sql(
    members: Sequence[dict[str, str]],
    anchor: datetime,
    source: Path,
) -> str:
    """Render ``04_seed_transactions.sql``: headers plus their line items.

    Headers are inserted **without** totals, so they take the column default of
    ``0``. The Checkpoint 2 trigger on ``transaction_items`` then fills them in
    from the line items. Nothing in this generator computes money: if the seed
    and the database ever disagreed about a total, the database would be right,
    so it is the only thing that should be doing the arithmetic.

    Every member gets one transaction first, then the remainder are handed out
    at random, so the top-10-spending query has a populated tail rather than a
    field of members with no history.
    """
    rng = random.Random(RANDOM_SEED)
    item_ids = [index for index, _ in enumerate(CATALOGUE, start=1)]
    popularity = [entry[4] for entry in CATALOGUE]

    window_start = anchor - timedelta(days=WINDOW_DAYS)
    window_seconds = int((anchor - window_start).total_seconds())

    member_ids = [row["membership_id"] for row in members]
    # One each, then fill the rest at random. Guarantees >= 1 per member.
    assignments = member_ids + [
        rng.choice(member_ids) for _ in range(TRANSACTION_COUNT - len(member_ids))
    ]

    header_values: list[str] = []
    line_values: list[str] = []

    for transaction_id, membership_id in enumerate(assignments, start=1):
        occurred = window_start + timedelta(seconds=rng.randrange(window_seconds))
        header_values.append(
            f"    ({transaction_id:>3}, {sql_str(membership_id)}, "
            f"'{occurred.strftime('%Y-%m-%d %H:%M:%S')}+00')"
        )

        basket_size = rng.randint(BASKET_MIN_ITEMS, BASKET_MAX_ITEMS)
        basket = weighted_sample(rng, item_ids, popularity, basket_size)
        for item_id in sorted(basket):
            _name, _manufacturer, cost, weight, _popularity = CATALOGUE[item_id - 1]
            quantity = rng.randint(QUANTITY_MIN, QUANTITY_MAX)
            # The unit cost/weight are snapshotted from the catalogue as it
            # stands now. In a live system these drift apart from items.cost as
            # prices change -- that divergence is the whole point of the columns.
            line_values.append(
                f"    ({transaction_id:>3}, {item_id:>2}, {quantity}, "
                f"{cost:.2f}, {weight:.3f})"
            )

    return (
        GENERATED_BANNER.format(
            description=(
                f"{len(header_values)} synthetic transactions ({len(line_values)} line items) "
                f"over the {WINDOW_DAYS} days to {anchor.date().isoformat()}.\n"
                f"-- Deterministic: random.Random({RANDOM_SEED}). Header totals are left at 0 "
                "and filled by the\n-- transaction_items trigger from 01_schema.sql."
            ),
            source=source.name,
        )
        + "\nBEGIN;\n\n"
        + "INSERT INTO transactions (transaction_id, membership_id, transaction_ts)\n"
        + "OVERRIDING SYSTEM VALUE\n"
        + "VALUES\n"
        + ",\n".join(header_values)
        + ";\n\n"
        + "-- Inserting these fires transaction_items_maintain_totals, which writes\n"
        + "-- transactions.total_items_price / total_items_weight for every header above.\n"
        + "INSERT INTO transaction_items\n"
        + "    (transaction_id, item_id, quantity, unit_cost_at_purchase, unit_weight_at_purchase)\n"
        + "VALUES\n"
        + ",\n".join(line_values)
        + ";\n\n"
        + "-- Fast-forward the identity sequence past the explicit IDs above.\n"
        + "SELECT setval(pg_get_serial_sequence('transactions', 'transaction_id'),\n"
        + "              (SELECT MAX(transaction_id) FROM transactions));\n\n"
        + "COMMIT;\n"
    )


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------


def self_check() -> None:
    """Assert the non-obvious bits still hold. Run with ``--self-check``.

    Deliberately assertion-based and framework-free: this is one script, and the
    properties worth pinning down are escaping, date handling and determinism.
    """
    assert sql_str("plain") == "'plain'"
    assert sql_str("O'Brien") == "'O''Brien'", "single quotes must be doubled"
    assert sql_str("''") == "''''''"
    assert sql_bool("TRUE ") == "true"
    try:
        sql_bool("yes")
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("sql_bool must reject anything but true/false")

    assert reference_datetime(Path("successful_applications_20260918_104159.csv")) == datetime(
        2026, 9, 18, 10, 41, 59
    )

    # Determinism: the same seed must produce byte-identical SQL.
    members = [
        {
            "membership_id": f"Test_{n:05d}",
            "first_name": "A",
            "last_name": "B",
            "email": "a@b.com",
            "birthday": "19900101",
            "above_18": "true",
            "mobile": "12345678",
        }
        for n in range(3)
    ]
    anchor = datetime(2026, 9, 18, 10, 41, 59)
    first = build_transactions_sql(members, anchor, Path("x_20260918_104159.csv"))
    second = build_transactions_sql(members, anchor, Path("x_20260918_104159.csv"))
    assert first == second, "same seed must give identical output"
    # The header INSERT must name exactly three columns. If a total ever creeps
    # into that list, the generator has started computing money and the trigger
    # is no longer the single source of truth.
    assert (
        "INSERT INTO transactions (transaction_id, membership_id, transaction_ts)\n" in first
    ), "the generator must not write totals; the trigger owns them"

    # Weighted draws are distinct and stay inside the population.
    rng = random.Random(1)
    drawn = weighted_sample(rng, [1, 2, 3, 4, 5], [10, 1, 1, 1, 1], 4)
    assert len(drawn) == len(set(drawn)) == 4
    assert set(drawn) <= {1, 2, 3, 4, 5}

    # Duplicate membership_ids are dropped, not silently backfilled.
    assert len({m["membership_id"] for m in members}) == len(members)

    print("self-check: OK")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def write_file(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` with LF endings.

    ``newline="\\n"`` is not optional: this is developed on Windows, and letting
    Python translate to CRLF would make the committed SQL churn depending on who
    regenerated it last.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    logger.info("Wrote %s (%d lines)", path.name, content.count("\n"))


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--section1-output",
        type=Path,
        default=None,
        help="Path to a successful_applications_*.csv. Defaults to the newest in "
        f"{DEFAULT_SECTION1_DIR}.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Where to write the seed SQL. Default: {DEFAULT_OUTPUT_DIR}.",
    )
    parser.add_argument(
        "--reference-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d"),
        default=None,
        help="Anchor for the synthetic transaction window (YYYY-MM-DD). "
        "Defaults to the run timestamp in the Section 1 filename.",
    )
    parser.add_argument("--self-check", action="store_true", help="Run assertions and exit.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
    )

    if args.self_check:
        self_check()
        return 0

    source = args.section1_output or find_latest_section1_output(DEFAULT_SECTION1_DIR)
    anchor = args.reference_date or reference_datetime(source)
    members = read_members(source, MEMBER_LIMIT)
    if not members:
        raise SystemExit(f"No members read from {source}; nothing to seed.")

    write_file(args.output_dir / "02_seed_members.sql", build_members_sql(members, source))
    write_file(args.output_dir / "03_seed_items.sql", build_items_sql(source))
    write_file(
        args.output_dir / "04_seed_transactions.sql",
        build_transactions_sql(members, anchor, source),
    )

    logger.info(
        "Seed complete: %d members, %d items, %d transactions anchored to %s",
        len(members),
        len(CATALOGUE),
        TRANSACTION_COUNT,
        anchor.date().isoformat(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
