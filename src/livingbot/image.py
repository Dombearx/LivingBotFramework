import asyncio
import base64
import logging
import os
from typing import Any

import httpx
import logfire
from pydantic_ai import Agent, ModelSettings

from livingbot import config, llm_config
from livingbot.prompts import (
    IMAGE_ENHANCER_SYSTEM_PROMPT,
    IMAGE_STYLE_PREFIX,
    MUGDA_IMAGE_IDENTITY,
    SELFIE_PERSONA,
)

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 3.0
_POLL_TIMEOUT_SECONDS = 180.0
# /runsync blocks server-side for up to ~90s before returning IN_QUEUE/IN_PROGRESS,
# so the client timeout has to be higher than that.
_RUNSYNC_TIMEOUT_SECONDS = 100.0

# Character present: reference-image edit model, keeps her identity consistent.
_SELFIE_ENDPOINT = "https://api.runpod.ai/v2/nano-banana-edit"
# No character: plain text-to-image, nothing to keep consistent.
_SCENERY_ENDPOINT = "https://api.runpod.ai/v2/qwen-image-t2i"

_MIME_TYPES = {".png": "image/png", ".jpeg": "image/jpeg", ".jpg": "image/jpeg"}


def _build_enhancer_agent() -> Agent[None, str]:
    return Agent(
        llm_config.build_chat_model(
            llm_config.PROMPT_ENHANCER_MODEL, reasoning_effort="low"
        ),
        name="prompt_enhancer",
        instructions=IMAGE_ENHANCER_SYSTEM_PROMPT,
        model_settings=ModelSettings(max_tokens=1000),
    )


async def _enhance_prompt(
    description: str,
    include_mugda: bool,
    outfit_description: str,
) -> str:
    parts: list[str] = [description]
    if include_mugda:
        persona = SELFIE_PERSONA
        if outfit_description:
            persona += f" She is wearing: {outfit_description}."
        parts.append(persona)
    user_message = " ".join(parts)
    agent = _build_enhancer_agent()
    with logfire.span("enhance_image_prompt", model=llm_config.PROMPT_ENHANCER_MODEL):
        result = await agent.run(user_message)
    return result.output or description


def _reference_images() -> list[str]:
    images = []
    for path in config.MUGDA_REFERENCE_IMAGE_PATHS:
        mime_type = _MIME_TYPES[path.suffix.lower()]
        encoded = base64.b64encode(path.read_bytes()).decode()
        images.append(f"data:{mime_type};base64,{encoded}")
    return images


async def _run_job(
    client: httpx.AsyncClient, base_url: str, api_key: str, payload: dict[str, Any]
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}"}
    with logfire.span("run_runpod_job", base_url=base_url) as span:
        response = await client.post(
            f"{base_url}/runsync",
            json={"input": payload},
            headers=headers,
            timeout=_RUNSYNC_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()

        job_id = data["id"]
        status = data["status"]
        deadline = asyncio.get_event_loop().time() + _POLL_TIMEOUT_SECONDS
        polls = 0
        while status in ("IN_QUEUE", "IN_PROGRESS"):
            if asyncio.get_event_loop().time() > deadline:
                span.set_attribute("polls", polls)
                raise TimeoutError(f"RunPod job {job_id} timed out")
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            polls += 1
            response = await client.get(
                f"{base_url}/status/{job_id}", headers=headers, timeout=10.0
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


async def generate_image(
    description: str,
    include_mugda: bool,
    outfit_description: str = "",
) -> bytes:
    api_key = os.environ["RUNPOD_API_KEY"]

    with logfire.span(
        "generate_image",
        include_mugda=include_mugda,
        has_outfit=bool(outfit_description),
    ) as span:
        scene = await _enhance_prompt(description, include_mugda, outfit_description)
        span.set_attribute("scene", scene)
        logger.info("Enhanced scene: %s", scene)

        prompt = IMAGE_STYLE_PREFIX
        if include_mugda:
            prompt += MUGDA_IMAGE_IDENTITY
        prompt += scene

        async with httpx.AsyncClient() as client:
            if include_mugda:
                payload: dict[str, Any] = {
                    "prompt": prompt,
                    "images": _reference_images(),
                    "enable_safety_checker": False,
                }
                output = await _run_job(client, _SELFIE_ENDPOINT, api_key, payload)
            else:
                payload = {
                    "prompt": prompt,
                    "seed": -1,
                    "enable_safety_checker": False,
                }
                output = await _run_job(client, _SCENERY_ENDPOINT, api_key, payload)

            span.set_attribute("cost", output.get("cost"))
            logger.info("RunPod job completed, cost=$%s", output.get("cost"))

            image_response = await client.get(output["result"], timeout=60.0)
            image_response.raise_for_status()
            image_bytes = image_response.content

        span.set_attribute("image_bytes", len(image_bytes))
        logger.info("Image generated (%d bytes)", len(image_bytes))
        return image_bytes
