from pathlib import Path

import pytest

from scripts.validate_alembic import alembic_heads, validate_alembic_heads


def test_current_repository_has_exactly_one_alembic_head() -> None:
    repository_root = Path(__file__).resolve().parents[2]

    assert alembic_heads(repository_root) == ("20260821_04",)


@pytest.mark.parametrize(
    ("heads", "expected_message"),
    [
        ((), "no head"),
        (("revision_a", "revision_b"), "multiple heads"),
    ],
)
def test_alembic_validator_fails_closed_for_invalid_head_counts(
    heads: tuple[str, ...],
    expected_message: str,
) -> None:
    errors = validate_alembic_heads(heads)

    assert len(errors) == 1
    assert expected_message in errors[0]
