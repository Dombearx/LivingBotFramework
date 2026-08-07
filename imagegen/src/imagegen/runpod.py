import asyncio
import logging
from typing import Any

import httpx
import logfire

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 3.0
POLL_TIMEOUT_SECONDS = 180.0
# /runsync blocks server-side for up to ~90s before returning IN_QUEUE/IN_PROGRESS,
# so the client timeout has to be higher than that.
RUNSYNC_TIMEOUT_SECONDS = 100.0
STATUS_TIMEOUT_SECONDS = 10.0
DOWNLOAD_TIMEOUT_SECONDS = 60.0

# Reference-image edit model, keeps the subject's identity consistent.
REFERENCE_ENDPOINT = "https://api.runpod.ai/v2/nano-banana-edit"
# Plain text-to-image, nothing to keep consistent.
TEXT_TO_IMAGE_ENDPOINT = "https://api.runpod.ai/v2/qwen-image-t2i"


async def run_job(
    client: httpx.AsyncClient, base_url: str, api_key: str, payload: dict[str, Any]
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}"}
    with logfire.span("run_runpod_job", base_url=base_url) as span:
        response = await client.post(
            f"{base_url}/runsync",
            json={"input": payload},
            headers=headers,
            timeout=RUNSYNC_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()

        job_id = data["id"]
        status = data["status"]
        deadline = asyncio.get_event_loop().time() + POLL_TIMEOUT_SECONDS
        polls = 0
        while status in ("IN_QUEUE", "IN_PROGRESS"):
            if asyncio.get_event_loop().time() > deadline:
                span.set_attribute("polls", polls)
                raise TimeoutError(f"RunPod job {job_id} timed out")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            polls += 1
            response = await client.get(
                f"{base_url}/status/{job_id}",
                headers=headers,
                timeout=STATUS_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            status = data["status"]

        span.set_attribute("polls", polls)
        if status != "COMPLETED":
            raise RuntimeError(
                f"RunPod job {job_id} ended with status {status}: {data}"
            )

        output: dict[str, Any] = data["output"]
        return output


async def generate(
    base_url: str, api_key: str, payload: dict[str, Any]
) -> tuple[bytes, float | None]:
    async with httpx.AsyncClient() as client:
        output = await run_job(client, base_url, api_key, payload)
        cost = output.get("cost")
        logger.info("RunPod job completed, cost=$%s", cost)

        response = await client.get(output["result"], timeout=DOWNLOAD_TIMEOUT_SECONDS)
        response.raise_for_status()
        image_bytes = response.content

    logger.info("Image generated (%d bytes)", len(image_bytes))
    return image_bytes, cost
