from types import SimpleNamespace

import pytest

from scripts import run_production_gate

pytestmark = pytest.mark.w7_production_gate


class MarkedItem:
    def __init__(
        self,
        nodeid: str = sorted(run_production_gate.REQUIRED_POSTGRES_NODEIDS)[0],
    ) -> None:
        self.nodeid = nodeid

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
    marked_item = MarkedItem()
    plugin.pytest_collection_modifyitems([marked_item])  # type: ignore[list-item]
    plugin.pytest_runtest_logreport(  # type: ignore[arg-type]
        SimpleNamespace(nodeid=marked_item.nodeid, skipped=True)
    )
    session = SimpleNamespace(
        config=SimpleNamespace(
            pluginmanager=SimpleNamespace(get_plugin=lambda _name: None)
        ),
        exitstatus=pytest.ExitCode.OK,
    )

    plugin.pytest_sessionfinish(session, pytest.ExitCode.OK)  # type: ignore[arg-type]

    assert any(
        reason == "required PostgreSQL tests skipped: " + marked_item.nodeid
        for reason in plugin.blocked_reasons()
    )
    assert session.exitstatus == pytest.ExitCode.TESTS_FAILED
    assert "BLOCKED" in capsys.readouterr().err


def test_required_postgres_plugin_blocks_missing_collection() -> None:
    plugin = run_production_gate.RequiredPostgresEvidencePlugin()

    reasons = plugin.blocked_reasons()

    assert "no required PostgreSQL integration tests were collected" in reasons
    assert any(
        reason.startswith("required PostgreSQL tests were not collected:")
        for reason in reasons
    )


def test_required_postgres_plugin_blocks_when_one_expected_test_disappears() -> None:
    missing_nodeid = sorted(run_production_gate.REQUIRED_POSTGRES_NODEIDS)[0]
    collected = [
        MarkedItem(nodeid)
        for nodeid in run_production_gate.REQUIRED_POSTGRES_NODEIDS
        if nodeid != missing_nodeid
    ]
    plugin = run_production_gate.RequiredPostgresEvidencePlugin()

    plugin.pytest_collection_modifyitems(collected)  # type: ignore[arg-type]

    assert plugin.missing_expected_nodeids == {missing_nodeid}
    assert any(
        missing_nodeid in reason
        for reason in plugin.blocked_reasons()
        if reason.startswith("required PostgreSQL tests were not collected:")
    )
