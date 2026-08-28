"""Require the VDDAI Alembic revision graph to have exactly one head."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def alembic_heads(repository_root: Path) -> tuple[str, ...]:
    """Return the repository's Alembic heads in deterministic order."""
    root = repository_root.resolve()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    script = ScriptDirectory.from_config(config)
    return tuple(sorted(script.get_heads()))


def validate_alembic_heads(heads: tuple[str, ...]) -> list[str]:
    """Return fail-closed revision-graph errors."""
    if len(heads) == 1:
        return []
    if not heads:
        return ["Alembic revision graph has no head."]
    return ["Alembic revision graph has multiple heads: " + ", ".join(sorted(heads))]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root. Defaults to the parent of scripts/.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    heads = alembic_heads(args.root)
    errors = validate_alembic_heads(heads)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"Alembic revision graph has exactly one head: {heads[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
