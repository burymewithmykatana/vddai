from types import SimpleNamespace

import pytest

from scripts import run_production_gate

pytestmark = pytest.mark.w7_production_gate


class MarkedItem:
    nodeid = "app/tests/test_postgres.py::test_required"

    @staticmethod
    def get_closest_marker(name: str) -> object | None:
        if name in {"w7_production_gate", "postgres_integration"}:
            return object()
        return None


def test_runner_blocks_before_pytest_when_postgres_url_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        run_production_gate.pytest,
        "main",
        lambda *_args, **_kwargs: pytest.fail("pytest must not run"),
    )

    exit_code = run_production_gate.run_production_gate(environ={})

    assert exit_code == pytest.ExitCode.TESTS_FAILED
    assert "BLOCKED" in capsys.readouterr().err


def test_runner_invokes_the_w7_marker_with_required_evidence_plugin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_pytest_main(
        arguments: list[str],
        *,
        plugins: list[object],
    ) -> pytest.ExitCode:
        captured["arguments"] = arguments
        captured["plugins"] = plugins
        return pytest.ExitCode.OK

    monkeypatch.setattr(run_production_gate.pytest, "main", fake_pytest_main)

    exit_code = run_production_gate.run_production_gate(
        environ={
            run_production_gate.POSTGRES_DATABASE_URL_ENV: (
                "postgresql+psycopg://test:test@localhost/test"
            )
        }
    )

    assert exit_code == pytest.ExitCode.OK
    assert captured["arguments"] == ["-q", "-m", "w7_production_gate"]
    plugins = captured["plugins"]
    assert isinstance(plugins, list)
    assert len(plugins) == 1
    assert isinstance(
        plugins[0],
        run_production_gate.RequiredPostgresEvidencePlugin,
    )


def test_required_postgres_plugin_blocks_skipped_evidence(
    capsys: pytest.CaptureFixture[str],
) -> None:
    plugin = run_production_gate.RequiredPostgresEvidencePlugin()
    plugin.pytest_collection_modifyitems([MarkedItem()])  # type: ignore[list-item]
    plugin.pytest_runtest_logreport(  # type: ignore[arg-type]
        SimpleNamespace(nodeid=MarkedItem.nodeid, skipped=True)
    )
    session = SimpleNamespace(
        config=SimpleNamespace(
            pluginmanager=SimpleNamespace(get_plugin=lambda _name: None)
        ),
        exitstatus=pytest.ExitCode.OK,
    )

    plugin.pytest_sessionfinish(session, pytest.ExitCode.OK)  # type: ignore[arg-type]

    assert plugin.blocked_reasons() == [
        "required PostgreSQL tests skipped: " + MarkedItem.nodeid
    ]
    assert session.exitstatus == pytest.ExitCode.TESTS_FAILED
    assert "BLOCKED" in capsys.readouterr().err


def test_required_postgres_plugin_blocks_missing_collection() -> None:
    plugin = run_production_gate.RequiredPostgresEvidencePlugin()

    assert plugin.blocked_reasons() == [
        "no required PostgreSQL integration tests were collected"
    ]
