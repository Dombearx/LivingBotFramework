"""Shared helpers for the RunPod image-generation smoke test scripts."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 3.0
_POLL_TIMEOUT_SECONDS = 180.0
# /runsync blocks server-side for up to ~90s before returning IN_QUEUE/IN_PROGRESS,
# so the client timeout has to be higher than that.
_RUNSYNC_TIMEOUT_SECONDS = 100.0


def run_job(base_url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}"}
    with httpx.Client(timeout=_RUNSYNC_TIMEOUT_SECONDS) as client:
        response = client.post(
            f"{base_url}/runsync", json={"input": payload}, headers=headers
        )
        response.raise_for_status()
        data = response.json()

        job_id = data["id"]
        status = data["status"]
        deadline = time.monotonic() + _POLL_TIMEOUT_SECONDS
        while status in ("IN_QUEUE", "IN_PROGRESS"):
            if time.monotonic() > deadline:
                raise TimeoutError(f"RunPod job {job_id} timed out")
            logger.info("Job %s still %s, polling...", job_id, status)
            time.sleep(_POLL_INTERVAL_SECONDS)
            response = client.get(f"{base_url}/status/{job_id}", headers=headers)
            response.raise_for_status()
            data = response.json()
            status = data["status"]

    if status != "COMPLETED":
        raise RuntimeError(f"RunPod job {job_id} ended with status {status}: {data}")

    output: dict[str, Any] = data["output"]
    return output


def download_image(image_url: str, output_path: Path) -> None:
    with httpx.Client(timeout=60.0) as client:
        response = client.get(image_url)
        response.raise_for_status()
        output_path.write_bytes(response.content)
