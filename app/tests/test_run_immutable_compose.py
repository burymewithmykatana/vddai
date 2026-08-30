import subprocess

import pytest

from scripts import run_immutable_compose

IMMUTABLE_REFERENCE = "ghcr.io/burymewithmykatana/vddai@sha256:" + "a" * 64


def test_digest_pinned_reference_is_accepted() -> None:
    assert (
        run_immutable_compose.validate_immutable_image_reference(IMMUTABLE_REFERENCE)
        == IMMUTABLE_REFERENCE
    )


def test_digest_pinned_reference_with_a_registry_port_is_accepted() -> None:
    image_reference = "localhost:5001/vddai@sha256:" + "b" * 64

    assert (
        run_immutable_compose.validate_immutable_image_reference(image_reference)
        == image_reference
    )


@pytest.mark.parametrize(
    "image_reference",
    [
        "ghcr.io/burymewithmykatana/vddai:latest",
        "ghcr.io/burymewithmykatana/vddai:sha-0123456789abcdef",
        "sha256:" + "a" * 64,
    ],
)
def test_mutable_or_unqualified_image_references_are_rejected(
    image_reference: str,
) -> None:
    with pytest.raises(
        run_immutable_compose.ImmutableComposeValidationError,
        match="canonical name@sha256",
    ):
        run_immutable_compose.validate_immutable_image_reference(image_reference)


def test_runner_validates_before_invoking_compose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_compose_runs(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Compose must not run for a mutable image reference.")

    monkeypatch.setattr(run_immutable_compose.subprocess, "run", fail_if_compose_runs)

    with pytest.raises(run_immutable_compose.ImmutableComposeValidationError):
        run_immutable_compose.run_immutable_compose(
            ["config", "--quiet"],
            environ={
                "VDDAI_APPLICATION_IMAGE": "ghcr.io/burymewithmykatana/vddai:latest",
                "VDDAI_ARTIFACTS_PATH": "D:/runtime-artifacts",
            },
        )


def test_runner_invokes_immutable_compose_for_a_digest_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_command: list[str] | None = None

    def fake_run(
        command: list[str], *, check: bool, input: str, text: bool
    ) -> subprocess.CompletedProcess[str]:
        nonlocal observed_command
        assert check is False
        assert text is True
        assert IMMUTABLE_REFERENCE in input
        assert "D:/runtime-artifacts:/app/artifacts:ro" in input
        observed_command = command
        return subprocess.CompletedProcess(command, returncode=0)

    monkeypatch.setattr(run_immutable_compose.subprocess, "run", fake_run)

    assert (
        run_immutable_compose.run_immutable_compose(
            ["config", "--quiet"],
            environ={
                "VDDAI_APPLICATION_IMAGE": IMMUTABLE_REFERENCE,
                "VDDAI_ARTIFACTS_PATH": "D:/runtime-artifacts",
            },
        )
        == 0
    )
    assert observed_command == [
        "docker",
        "compose",
        "-f",
        "-",
        "config",
        "--quiet",
    ]


def test_runner_requires_provisioned_runtime_artifacts() -> None:
    with pytest.raises(
        run_immutable_compose.ImmutableComposeValidationError,
        match="VDDAI_ARTIFACTS_PATH",
    ):
        run_immutable_compose.run_immutable_compose(
            ["config", "--quiet"],
            environ={"VDDAI_APPLICATION_IMAGE": IMMUTABLE_REFERENCE},
        )
