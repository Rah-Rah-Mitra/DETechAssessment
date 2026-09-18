"""Unit tests for the pure transformations of Checkpoint 2."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from conftest import cleaned, source_frame

from membership_pipeline import transform

REFERENCE = date(2022, 1, 1)


# ---------------------------------------------------------------------------
# Name splitting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "first", "last"),
    [
        ("William Dixon", "William", "Dixon"),
        # Salutations, with and without the trailing dot.
        ("Mr. Scott Martinez", "Scott", "Martinez"),
        ("Mrs. Jessica Gibson", "Jessica", "Gibson"),
        ("Miss Katherine Brennan", "Katherine", "Brennan"),
        ("Dr. Jeffrey Spencer", "Jeffrey", "Spencer"),
        ("Mr Ann Lee", "Ann", "Lee"),
        ("MR. LOUD PERSON", "LOUD", "PERSON"),
        # Post-nominal suffixes.
        ("Sean Wang DDS", "Sean", "Wang"),
        ("Arthur Hall MD", "Arthur", "Hall"),
        ("Alyssa Williams DVM", "Alyssa", "Williams"),
        ("Gerald Hall PhD", "Gerald", "Hall"),
        ("Joshua Ellis Jr.", "Joshua", "Ellis"),
        ("Gregory Hill III", "Gregory", "Hill"),
        # Both at once.
        ("Mr. Larry Grimes MD", "Larry", "Grimes"),
        ("Dr. Courtney Copeland DVM", "Courtney", "Copeland"),
        # Middle names stay with the surname rather than being dropped.
        ("Mary Ann Smith", "Mary", "Ann Smith"),
        # A mononym has a first name but no surname.
        ("Cher", "Cher", ""),
        # Messy whitespace must not create empty tokens.
        ("  Double  Space  ", "Double", "Space"),
        ("\tTabbed\tName\t", "Tabbed", "Name"),
    ],
)
def test_name_splits_into_first_and_last(name: str, first: str, last: str) -> None:
    result = cleaned(name=[name])
    assert result["first_name"][0] == first
    assert result["last_name"][0] == last


@pytest.mark.parametrize("name", [None, "", "   ", "\t", "Mr.", "Dr."])
def test_name_without_a_usable_value_yields_nulls(name: str | None) -> None:
    """Absent names -- including a bare salutation -- leave nothing behind."""
    result = cleaned(name=[name])
    assert result["first_name"][0] is None
    assert result["last_name"][0] is None


def test_lone_suffix_is_kept_as_a_name() -> None:
    """A suffix is only stripped when a name would remain."""
    result = cleaned(name=["MD"])
    assert result["first_name"][0] == "MD"
    assert result["last_name"][0] == ""


# ---------------------------------------------------------------------------
# Birthday parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1986/01/10", date(1986, 1, 10)),   # %Y/%m/%d
        ("1974-09-10", date(1974, 9, 10)),   # %Y-%m-%d
        ("02/27/1974", date(1974, 2, 27)),   # %m/%d/%Y -- slash means month first
        ("14-03-1973", date(1973, 3, 14)),   # %d-%m-%Y -- dash means day first
        ("12/09/1992", date(1992, 12, 9)),   # ambiguous digits, resolved by separator
        ("09-11-2017", date(2017, 11, 9)),   # the same digits with the other separator
        (" 1986/01/10 ", date(1986, 1, 10)),  # surrounding whitespace tolerated
        ("2004-02-29", date(2004, 2, 29)),   # a real leap day
    ],
)
def test_each_accepted_birthday_format_parses(raw: str, expected: date) -> None:
    assert cleaned(birthday=[raw])["birthday_date"][0] == expected


@pytest.mark.parametrize(
    "raw",
    [
        "1996/02/31",   # 31 February does not exist
        "2021-02-29",   # 2021 is not a leap year
        "1986/13/10",   # month 13
        "not a date",
        "19860110",     # unseparated, deliberately not accepted
        "",
        None,
    ],
)
def test_unparseable_birthday_becomes_null_not_an_exception(raw: str | None) -> None:
    """Monadic safety: bad data degrades, it does not raise."""
    result = cleaned(birthday=[raw])
    assert result["birthday_date"][0] is None
    assert result["birthday_ymd"][0] is None
    assert result["age"][0] is None


def test_birthday_is_formatted_as_yyyymmdd() -> None:
    result = cleaned(birthday=["02/05/1968"])
    assert result["birthday_ymd"][0] == "19680205"


# ---------------------------------------------------------------------------
# Age and above_18
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("birthday", "age", "above_18"),
    [
        ("2003-01-01", 19, True),    # turns 19 exactly on the reference date
        ("2002-12-31", 19, True),    # the day either side of that boundary
        ("2003-01-02", 18, False),   # exactly 18 -- "over 18" excludes them
        ("2003-06-15", 18, False),
        ("2003-12-31", 18, False),
        ("2004-01-01", 18, False),   # turns 18 exactly on the reference date
        ("2004-01-02", 17, False),
        ("2004-02-29", 17, False),   # leap day: birthday has not come round in 2022
        ("2022-01-01", 0, False),    # born on the reference date
        ("1900-01-01", 122, True),
    ],
)
def test_age_and_above_18_at_the_boundaries(birthday: str, age: int, above_18: bool) -> None:
    result = cleaned(birthday=[birthday])
    assert result["age"][0] == age
    assert result["above_18"][0] is above_18


def test_leap_day_birthday_the_year_before_it_recurs() -> None:
    """A 29 February birthday assessed on 1 March of a non-leap year."""
    result = transform.clean(source_frame(birthday=["2004-02-29"]), date(2022, 3, 1)).collect()
    assert result["age"][0] == 18


def test_reference_date_is_a_parameter_not_a_global() -> None:
    frame = source_frame(birthday=["2003-06-15"])
    assert transform.clean(frame, date(2022, 1, 1)).collect()["age"][0] == 18
    assert transform.clean(frame, date(2030, 1, 1)).collect()["age"][0] == 26


def test_above_18_is_null_when_the_birthday_is_unreadable() -> None:
    """transform reports 'unknown', not False -- validate decides what that means."""
    assert cleaned(birthday=["not a date"])["above_18"][0] is None


# ---------------------------------------------------------------------------
# Mobile
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("40601711", "40601711"),
        ("6655 1251", "66551251"),
        (" 1234 5678 ", "12345678"),
        ("12 34 56 78", "12345678"),
        ("737931", "737931"),        # short numbers are normalised, then rejected later
        ("6655-1251", "6655-1251"),  # only whitespace is stripped, not punctuation
        (None, None),
    ],
)
def test_mobile_whitespace_is_stripped(raw: str | None, expected: str | None) -> None:
    assert cleaned(mobile=[raw])["mobile_normalised"][0] == expected


# ---------------------------------------------------------------------------
# Purity
# ---------------------------------------------------------------------------


def test_clean_is_lazy_and_leaves_its_input_untouched() -> None:
    frame = source_frame(name=["Mr. Ann Lee"], birthday=["14-03-1973"], mobile=["6655 1251"])
    before = dict(frame.collect_schema())

    result = transform.clean(frame, REFERENCE)

    assert isinstance(result, pl.LazyFrame), "clean() must not materialise"
    assert dict(frame.collect_schema()) == before, "clean() mutated its input frame"


def test_clean_adds_derived_columns_without_overwriting_the_raw_ones() -> None:
    result = cleaned(name=["Ann Lee"], email=["a@x.com"], birthday=["14-03-1973"], mobile=["6655 1251"])

    assert result["birthday"][0] == "14-03-1973", "raw birthday must survive for the audit trail"
    assert result["mobile"][0] == "6655 1251", "raw mobile must survive for the audit trail"
    assert result["birthday_ymd"][0] == "19730314"
    assert result["mobile_normalised"][0] == "66551251"


def test_expression_builders_return_expressions() -> None:
    """Every public builder is a pure Expr factory, safe to compose anywhere."""
    for builder in (
        transform.name_token_expr,
        transform.core_name_token_expr,
        transform.first_name_expr,
        transform.last_name_expr,
        transform.birthday_date_expr,
        transform.birthday_ymd_expr,
        transform.normalised_mobile_expr,
    ):
        assert isinstance(builder(), pl.Expr), builder.__name__
    assert isinstance(transform.age_expr(REFERENCE), pl.Expr)
    assert isinstance(transform.above_18_expr(REFERENCE), pl.Expr)
