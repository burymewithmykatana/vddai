import subprocess

import pytest

from scripts import validate_immutable_image

SOURCE = "https://github.com/burymewithmykatana/vddai"
REVISION = "a" * 40
VERSION = "0.1.0"


def _inspect_payload(*, labels: dict[str, str], image_id: str = "sha256:abc") -> str:
    return (
        "["
        '{"Id": "'
        + image_id
        + '", "Config": {"Labels": '
        + str(labels).replace("'", '"')
        + "}}]"
    )


def test_validate_image_identity_accepts_matching_oci_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    labels = {
        validate_immutable_image.OCI_SOURCE_LABEL: SOURCE,
        validate_immutable_image.OCI_REVISION_LABEL: REVISION,
        validate_immutable_image.OCI_VERSION_LABEL: VERSION,
    }
    monkeypatch.setattr(
        validate_immutable_image.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=_inspect_payload(labels=labels), stderr=""
        ),
    )

    assert (
        validate_immutable_image.validate_image_identity(
            "vddai:test", source=SOURCE, revision=REVISION, version=VERSION
        )
        == "sha256:abc"
    )


def test_validate_image_identity_rejects_a_mismatched_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    labels = {
        validate_immutable_image.OCI_SOURCE_LABEL: SOURCE,
        validate_immutable_image.OCI_REVISION_LABEL: "b" * 40,
        validate_immutable_image.OCI_VERSION_LABEL: VERSION,
    }
    monkeypatch.setattr(
        validate_immutable_image.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=_inspect_payload(labels=labels), stderr=""
        ),
    )

    with pytest.raises(
        validate_immutable_image.ImmutableImageValidationError,
        match="source-identity labels do not match",
    ):
        validate_immutable_image.validate_image_identity(
            "vddai:test", source=SOURCE, revision=REVISION, version=VERSION
        )


def test_validate_image_identity_requires_a_full_lowercase_sha() -> None:
    with pytest.raises(
        validate_immutable_image.ImmutableImageValidationError,
        match="full lowercase SHA",
    ):
        validate_immutable_image.validate_image_identity(
            "vddai:test", source=SOURCE, revision="not-a-sha", version=VERSION
        )


def test_inspect_image_reports_docker_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        validate_immutable_image.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.CalledProcessError(1, ["docker"], stderr="image missing")
        ),
    )

    with pytest.raises(
        validate_immutable_image.ImmutableImageValidationError,
        match="image missing",
    ):
        validate_immutable_image.inspect_image("missing")
