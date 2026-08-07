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

DEFAULT_IMAGE_SERVICE_URL = "http://localhost:8100"
# The service polls RunPod for up to three minutes before giving up, so this has
# to be longer than its own timeout or we abandon jobs that would have finished.
_REQUEST_TIMEOUT_SECONDS = 300.0

_MIME_TYPES = {".png": "image/png", ".jpeg": "image/jpeg", ".jpg": "image/jpeg"}


def _image_service_url() -> str:
    return os.environ.get("IMAGE_SERVICE_URL", DEFAULT_IMAGE_SERVICE_URL)


def _build_enhancer_agent() -> Agent[None, str]:
    return Agent(
        llm_config.build_chat_model(
            llm_config.PROMPT_ENHANCER_MODEL, reasoning_effort="low"
        ),
        name="prompt_enhancer",
        instructions=IMAGE_ENHANCER_SYSTEM_PROMPT,
        model_settings=ModelSettings(max_tokens=3000),
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


async def _request_image(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{_image_service_url()}{endpoint}"
    with logfire.span("call_image_service", endpoint=endpoint):
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url, json=payload, timeout=_REQUEST_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result


async def generate_image(
    description: str,
    include_mugda: bool,
    outfit_description: str = "",
) -> bytes:
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

        if include_mugda:
            result = await _request_image(
                "/generate-with-reference",
                {"prompt": prompt, "reference_images": _reference_images()},
            )
        else:
            result = await _request_image("/generate", {"prompt": prompt})

        span.set_attribute("cost", result["cost"])
        logger.info("Image generated, cost=$%s", result["cost"])

        image_bytes = base64.b64decode(result["image_base64"])
        span.set_attribute("image_bytes", len(image_bytes))
        return image_bytes
