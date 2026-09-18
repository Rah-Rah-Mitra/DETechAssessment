"""Unit tests for the validity predicates and membership IDs of Checkpoint 3."""

from __future__ import annotations

import hashlib

import polars as pl
import pytest
from conftest import source_frame, validated

from membership_pipeline import transform, validate

#: A known SHA-256 vector, verifiable independently:
#:   $ printf '19860110' | sha256sum
#:   3864b579395a2aa05673fc20b529368e8d96012c1935514bc24d6f60e9aa068b
KNOWN_BIRTHDAY = "19860110"
KNOWN_DIGEST = "3864b579395a2aa05673fc20b529368e8d96012c1935514bc24d6f60e9aa068b"


def _valid(**overrides: str) -> dict[str, list[str]]:
    """An application that passes every rule, with individual fields overridable."""
    row = {
        "name": "Ann Lee",
        "email": "ann@example.com",
        "birthday": "1986/01/10",
        "mobile": "40601711",
    }
    row.update(overrides)
    return {key: [value] for key, value in row.items()}


# ---------------------------------------------------------------------------
# Individual predicates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        ("ann@emailprovider.com", True),
        ("ann@emailprovider.net", True),
        ("ann@example.com", True),
        ("ann@example.net", True),
        ("ANN@EXAMPLE.COM", True),       # case-insensitive
        ("  ann@example.com  ", True),   # whitespace tolerated
        ("ann@example.org", False),
        ("ann@example.biz", False),
        ("ann@example.info", False),
        ("ann@example.net.org", False),  # the suffix must be at the end
        ("ann@example.com.sg", False),
        ("not-an-email", False),
        (None, False),
    ],
)
def test_email_predicate(email: str | None, expected: bool) -> None:
    result = pl.LazyFrame({"email": [email]}, schema={"email": pl.String}).select(
        ok=validate.valid_email_expr()
    ).collect()
    assert result["ok"][0] is expected


@pytest.mark.parametrize(
    ("mobile", "expected"),
    [
        ("40601711", True),
        ("6655 1251", True),      # whitespace stripped before the check
        (" 1234 5678 ", True),
        ("00000000", True),       # eight digits is eight digits
        ("7379310", False),       # seven
        ("123456789", False),     # nine
        ("737931", False),
        ("6655-1251", False),     # punctuation is not whitespace
        ("abcdefgh", False),
        ("1234567a", False),
        ("", False),
        (None, False),
    ],
)
def test_mobile_predicate(mobile: str | None, expected: bool) -> None:
    ok = (
        transform.clean(source_frame(mobile=[mobile]))
        .select(ok=validate.valid_mobile_expr())
        .collect()["ok"][0]
    )
    assert ok is expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Ann Lee", True),
        ("Cher", True),
        ("Mr. Ann Lee", True),
        ("Mr.", False),   # a salutation alone is not a name
        ("", False),
        ("   ", False),
        (None, False),
    ],
)
def test_name_predicate(name: str | None, expected: bool) -> None:
    ok = (
        transform.clean(source_frame(name=[name]))
        .select(ok=validate.has_name_expr())
        .collect()["ok"][0]
    )
    assert ok is expected


@pytest.mark.parametrize(
    ("birthday", "expected"),
    [("1986/01/10", True), ("14-03-1973", True), ("1996/02/31", False), (None, False)],
)
def test_parseable_birthday_predicate(birthday: str | None, expected: bool) -> None:
    ok = (
        transform.clean(source_frame(birthday=[birthday]))
        .select(ok=validate.parseable_birthday_expr())
        .collect()["ok"][0]
    )
    assert ok is expected


# ---------------------------------------------------------------------------
# Null safety
# ---------------------------------------------------------------------------


def test_no_predicate_ever_returns_null() -> None:
    """A null verdict would make LazyFrame.filter drop the row from both outputs."""
    frame = transform.clean(
        source_frame(name=[None], email=[None], birthday=[None], mobile=[None])
    )
    for reason, passes in validate.predicates():
        value = frame.select(ok=passes).collect()["ok"][0]
        assert value is not None, f"{reason} returned null"


def test_is_successful_is_never_null_for_an_all_null_row() -> None:
    result = validated(name=[None], email=[None], birthday=[None], mobile=[None])
    assert result["is_successful"][0] is False


# ---------------------------------------------------------------------------
# Rejection reasons
# ---------------------------------------------------------------------------


def test_successful_application_has_an_empty_reason() -> None:
    result = validated(**_valid())
    assert result["is_successful"][0] is True
    assert result["rejection_reason"][0] == ""


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"name": ""}, "missing_name"),
        ({"birthday": "2010-07-12"}, "under_18"),
        ({"mobile": "737931"}, "invalid_mobile"),
        ({"email": "ann@example.biz"}, "invalid_email"),
        ({"birthday": "1996/02/31"}, "unparseable_birthday"),
    ],
)
def test_each_rule_reports_its_own_reason(overrides: dict, expected: str) -> None:
    result = validated(**_valid(**overrides))
    assert result["rejection_reason"][0] == expected
    assert result["is_successful"][0] is False


def test_every_failed_rule_is_reported_not_just_the_first() -> None:
    result = validated(**_valid(birthday="2010-07-12", mobile="737931", email="ann@example.biz"))
    assert result["rejection_reason"][0] == "under_18;invalid_mobile;invalid_email"


def test_unparseable_birthday_does_not_also_claim_under_18() -> None:
    """We never read an age, so asserting one would be a lie in the audit file."""
    result = validated(**_valid(birthday="1996/02/31", mobile="737931"))
    assert result["rejection_reason"][0] == "unparseable_birthday;invalid_mobile"


def test_reason_order_is_stable() -> None:
    """The column must be diffable across runs, so the order is fixed."""
    assert [reason for reason, _ in validate.predicates()] == [
        "missing_name",
        "unparseable_birthday",
        "under_18",
        "invalid_mobile",
        "invalid_email",
    ]


# ---------------------------------------------------------------------------
# Membership ID
# ---------------------------------------------------------------------------


def test_membership_id_matches_a_known_sha256_vector() -> None:
    assert hashlib.sha256(KNOWN_BIRTHDAY.encode()).hexdigest() == KNOWN_DIGEST

    result = validated(**_valid(name="Mr. William Dixon", birthday="1986/01/10"))
    assert result["membership_id"][0] == f"Dixon_{KNOWN_DIGEST[:5]}"
    assert result["membership_id"][0] == "Dixon_3864b"


def test_membership_id_uses_five_hex_characters() -> None:
    membership_id = validated(**_valid())["membership_id"][0]
    _, _, digest = membership_id.rpartition("_")
    assert len(digest) == 5
    assert set(digest) <= set("0123456789abcdef")


def test_membership_id_uses_the_surname_after_stripping_honorifics() -> None:
    result = validated(**_valid(name="Dr. Courtney Copeland DVM"))
    assert result["membership_id"][0].startswith("Copeland_")


def test_mononym_still_receives_an_id() -> None:
    """An applicant with no surname is eligible; their ID simply has an empty prefix."""
    result = validated(**_valid(name="Cher"))
    assert result["is_successful"][0] is True
    assert result["membership_id"][0] == f"_{KNOWN_DIGEST[:5]}"


def test_rejected_applications_have_no_membership_id() -> None:
    result = validated(**_valid(mobile="737931"))
    assert result["membership_id"][0] is None


def test_identical_surname_and_birthday_collide_by_construction() -> None:
    """A documented limit of the ID scheme the brief specifies, not a defect.

    The ID is a function of surname and birthday alone, so two distinct people
    sharing both receive the same ID -- as happens once in the sample data.
    """
    result = validated(
        name=["Kenneth Williamson", "Bethany Williamson"],
        email=["k@example.com", "b@example.com"],
        birthday=["10-03-1954", "1954/03/10"],  # same date, different source formats
        mobile=["40601711", "40601712"],
    )
    assert result["is_successful"].all()
    assert result["membership_id"][0] == result["membership_id"][1]


# ---------------------------------------------------------------------------
# Purity
# ---------------------------------------------------------------------------


def test_validate_is_lazy_and_leaves_its_input_untouched() -> None:
    frame = transform.clean(source_frame(**_valid()))
    before = dict(frame.collect_schema())

    result = validate.validate(frame)

    assert isinstance(result, pl.LazyFrame), "validate() must not materialise"
    assert dict(frame.collect_schema()) == before, "validate() mutated its input frame"


def test_validate_drops_no_rows() -> None:
    """Partitioning belongs to output.py; validate only labels."""
    result = validated(
        name=["Ann Lee", "", None, "Kid Person"],
        email=["a@x.com", "b@x.com", "c@x.com", "d@x.biz"],
        birthday=["1986/01/10", "1986/01/10", "bad", "2010-07-12"],
        mobile=["40601711", "737931", None, "40601711"],
    )
    assert result.height == 4
    assert result["is_successful"].to_list() == [True, False, False, False]
