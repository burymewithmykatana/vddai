"""Measure the fixed Week 9 workload on an explicitly disposable local API."""

import argparse
import asyncio
import json
import math
import re
import secrets
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import httpx2
from PIL import Image, ImageDraw

from scripts.prove_real_inference import (
    InferenceGateError,
    validate_completed_prediction,
)


@dataclass(frozen=True)
class Phase:
    name: str
    seconds: int
    jobs: int


PHASES = (Phase("warmup", 300, 10), Phase("steady", 900, 60))
TARGETS = {
    "api_p95_seconds": 1,
    "job_p95_seconds": 15,
    "inference_p95_seconds": 5,
    "unexpected_failure_fraction": 0.01,
}
MAX_RESPONSE_BYTES = 256 * 1024
REQUEST_TIMEOUT_SECONDS = 4.0
FORMATS = ("PNG", "JPEG", "WEBP")
SIZES = ((384, 288), (640, 480), (1024, 768))


class SoakError(RuntimeError):
    """A safe reason code for the aggregate receipt."""


def percentile95(values: list[float]) -> float | None:
    if not values:
        return None
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def sleep_until(deadline: float) -> None:
    remaining = deadline - time.monotonic()
    if remaining > 0:
        time.sleep(remaining)


class LocalPilot:
    def __init__(self, port: int, service: str, package: str) -> None:
        if not 1024 <= port <= 65535 or not re.fullmatch(
            r"vddai-w9d5-[a-z0-9-]{6,40}", service
        ):
            raise SoakError("invalid_disposable_target")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{7,99}", package):
            raise SoakError("invalid_expected_package")
        self.port = port
        self.service = service
        self.package = package
        self.api_seconds: list[float] = []

    def request(
        self,
        method: str,
        path: str,
        expected: int,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        measured: bool = False,
        deadline: float | None = None,
    ) -> dict:
        start = time.monotonic()
        request_deadline = start + REQUEST_TIMEOUT_SECONDS
        timeout_reason = "local_transport_failed"
        if deadline is not None and deadline <= request_deadline:
            request_deadline = deadline
            timeout_reason = "job_deadline_exceeded"
        try:
            contents = asyncio.run(
                self._exchange(method, path, expected, body, headers, request_deadline)
            )
            value = json.loads(contents)
            if not isinstance(value, dict):
                raise SoakError("invalid_response_shape")
            if deadline is not None and time.monotonic() >= deadline:
                raise SoakError("job_deadline_exceeded")
            return value
        except TimeoutError as exc:
            raise SoakError(timeout_reason) from exc
        except (OSError, httpx2.RequestError) as exc:
            raise SoakError("local_transport_failed") from exc
        except (ValueError, RecursionError) as exc:
            raise SoakError("invalid_json_response") from exc
        finally:
            if measured:
                self.api_seconds.append(time.monotonic() - start)

    async def _exchange(
        self,
        method: str,
        path: str,
        expected: int,
        body: bytes | None,
        headers: dict[str, str] | None,
        deadline: float,
    ) -> bytearray:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        if not path.startswith("/"):
            raise SoakError("invalid_request_path")
        contents = bytearray()
        # A socket inactivity timeout would reset during a slow response body.
        async with asyncio.timeout(remaining), httpx2.AsyncClient(
            trust_env=False, follow_redirects=False, timeout=None
        ) as client:
            async with client.stream(
                method,
                f"http://127.0.0.1:{self.port}{path}",
                content=body,
                headers={"Accept-Encoding": "identity", **(headers or {})},
            ) as response:
                if response.status_code != expected:
                    raise SoakError(f"unexpected_http_status_{response.status_code}")
                async for chunk in response.aiter_raw():
                    if len(contents) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise SoakError("response_too_large")
                    contents.extend(chunk)
        return contents

    def check_target(self) -> None:
        health = self.request("GET", "/health", 200)
        if health != {
            "status": "ok",
            "environment": "development",
            "service": self.service,
        }:
            raise SoakError("unexpected_local_service_identity")
        if self.request("GET", "/health/db", 200) != {
            "status": "ok",
            "database": "connected",
        }:
            raise SoakError("database_not_ready")
        model = self.request("GET", "/health/model", 200)
        if model.get("status") != "selected" or model.get("package_id") != self.package:
            raise SoakError("unexpected_model_package")

    def create_owner(self) -> dict[str, str]:
        tag = secrets.token_hex(12)
        user = {
            "email": f"pilot-{tag}@example.com",
            "password": secrets.token_urlsafe(32),
        }
        headers = {"Content-Type": "application/json"}
        self.request(
            "POST",
            "/auth/register",
            201,
            body=json.dumps({**user, "full_name": "Synthetic pilot"}).encode(),
            headers=headers,
        )
        reply = self.request(
            "POST", "/auth/login", 200, body=json.dumps(user).encode(), headers=headers
        )
        token = reply.get("access_token")
        if not isinstance(token, str) or not token:
            raise SoakError("invalid_session")
        return {"Authorization": f"Bearer {token}"}


def synthetic_upload(index: int) -> tuple[bytes, str]:
    fmt = FORMATS[index % len(FORMATS)]
    width, height = SIZES[(index // len(FORMATS)) % len(SIZES)]
    image = Image.new("RGB", (width, height), (64 + index % 96, 120, 192 - index % 96))
    draw = ImageDraw.Draw(image)
    for offset in range(0, width, 24):
        draw.line(
            (offset, 0, width - offset, height), fill=(offset % 256, 210, 90), width=2
        )
    output = BytesIO()
    image.save(output, format=fmt)
    boundary = "vddai-pilot-" + secrets.token_hex(12)
    media = fmt.lower()
    prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="pilot.{media}"\r\n'
        f"Content-Type: image/{media}\r\n\r\n"
    ).encode("ascii")
    return (
        prefix + output.getvalue() + f"\r\n--{boundary}--\r\n".encode("ascii"),
        f"multipart/form-data; boundary={boundary}",
    )


def run_soak(pilot: LocalPilot, report: dict) -> None:
    pilot.check_target()
    owners = (pilot.create_owner(), pilot.create_owner())
    states = Counter()
    accepted_ids: set[int] = set()
    job_seconds: list[float] = []
    inference_seconds: list[float] = []
    start = time.monotonic()
    cursor = start
    total = 0
    try:
        for phase in PHASES:
            phase_report = {
                "name": phase.name,
                "planned": phase.jobs,
                "upload_attempts": 0,
                "accepted": 0,
                "completed": 0,
            }
            report["phases"].append(phase_report)
            for number in range(phase.jobs):
                spacing = phase.seconds / phase.jobs
                scheduled = cursor + number * spacing
                sleep_until(scheduled)
                if time.monotonic() - scheduled >= spacing:
                    raise SoakError("workload_fell_behind")
                body, content_type = synthetic_upload(total)
                owner = owners[total % 2]
                job_start = time.monotonic()
                deadline = job_start + TARGETS["job_p95_seconds"]
                phase_report["upload_attempts"] += 1
                reply = pilot.request(
                    "POST",
                    "/predictions",
                    202,
                    body=body,
                    headers={**owner, "Content-Type": content_type},
                    measured=True,
                    deadline=deadline,
                )
                prediction_id = reply.get("prediction_id")
                if (
                    type(prediction_id) is not int
                    or prediction_id <= 0
                    or reply.get("status") != "queued"
                ):
                    raise SoakError("invalid_queue_receipt")
                if prediction_id in accepted_ids:
                    raise SoakError("duplicate_queue_receipt")
                accepted_ids.add(prediction_id)
                phase_report["accepted"] += 1
                path = f"/predictions/{prediction_id}"
                while time.monotonic() < deadline:
                    observation = pilot.request(
                        "GET",
                        path,
                        200,
                        headers=owner,
                        measured=True,
                        deadline=deadline,
                    )
                    state = observation.get("status")
                    if state in ("queued", "processing"):
                        states[state] += 1
                        sleep_until(min(deadline, time.monotonic() + 0.25))
                        continue
                    if state != "completed":
                        raise SoakError("non_successful_terminal_result")
                    try:
                        outcome = validate_completed_prediction(observation)
                        inference_latency = outcome["latency_ms"] / 1000
                    except (InferenceGateError, TypeError, OverflowError) as exc:
                        raise SoakError("invalid_terminal_result") from exc
                    if (
                        outcome["package_id"] != pilot.package
                        or type(outcome["prediction_id"]) is not int
                        or outcome["prediction_id"] != prediction_id
                    ):
                        raise SoakError("terminal_identity_changed")
                    latency = time.monotonic() - job_start
                    if latency >= TARGETS["job_p95_seconds"]:
                        raise SoakError("job_deadline_exceeded")
                    job_seconds.append(latency)
                    inference_seconds.append(inference_latency)
                    phase_report["completed"] += 1
                    total += 1
                    break
                else:
                    raise SoakError("job_deadline_exceeded")
            cursor += phase.seconds
            print(
                f'{phase.name}: {phase_report["completed"]} jobs completed', flush=True
            )
        sleep_until(cursor)
        pilot.check_target()
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - start, 3)
        report["intermediate_status_reads"] = dict(states)
        report["api_samples"] = len(pilot.api_seconds)
        report["api_p95_seconds"] = percentile95(pilot.api_seconds)
        report["job_p95_seconds"] = percentile95(job_seconds)
        report["inference_p95_seconds"] = percentile95(inference_seconds)
        report["completed"] = total
        attempted = sum(phase["upload_attempts"] for phase in report["phases"])
        report["unexpected_failures"] = attempted - total
        report["unexpected_failure_fraction"] = (
            (attempted - total) / attempted if attempted else None
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--expected-service", required=True)
    parser.add_argument("--package-id", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        pilot = LocalPilot(args.port, args.expected_service, args.package_id)
    except SoakError as exc:
        parser.exit(2, f"{exc}\n")

    report = {
        "schema_version": "vddai.local_pilot_soak.v1",
        "started_utc": datetime.now(UTC).isoformat(),
        "package_id": pilot.package,
        "workload": [asdict(phase) for phase in PHASES],
        "phases": [],
        "targets": TARGETS,
        "result": "failed",
    }
    try:
        handle = args.report.open("x", encoding="utf-8")
    except OSError:
        parser.exit(2, "could_not_create_report\n")
    with handle as output:
        try:
            run_soak(pilot, report)
        except SoakError as exc:
            report["error"] = str(exc)
        except KeyboardInterrupt:
            report["error"] = "interrupted"
        else:
            latency_metrics = (
                "api_p95_seconds",
                "job_p95_seconds",
                "inference_p95_seconds",
            )
            if any(
                report[name] is None or report[name] > TARGETS[name]
                for name in latency_metrics
            ):
                report["error"] = "latency_target_exceeded"
            else:
                report["result"] = "passed"
        finally:
            report["finished_utc"] = datetime.now(UTC).isoformat()
            json.dump(report, output, indent=2)
    return 0 if report["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
