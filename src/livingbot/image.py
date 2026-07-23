import asyncio
import base64
import copy
import json
import logging
import os
import random
from importlib.resources import files
from typing import Any

import httpx
import logfire
from pydantic_ai import Agent, ModelSettings

from livingbot import llm_config
from livingbot.prompts import IMAGE_ENHANCER_SYSTEM_PROMPT, SELFIE_PERSONA

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 3.0
_POLL_TIMEOUT_SECONDS = 120.0


def _build_enhancer_agent() -> Agent[None, str]:
    return Agent(
        llm_config.build_chat_model(llm_config.PROMPT_ENHANCER_MODEL),
        name="prompt_enhancer",
        instructions=IMAGE_ENHANCER_SYSTEM_PROMPT,
        model_settings=ModelSettings(max_tokens=400, temperature=0.7),
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


def _load_workflow() -> dict[str, Any]:
    workflow_text = files("livingbot.workflows").joinpath("workflow.json").read_text()
    workflow: dict[str, Any] = json.loads(workflow_text)
    return workflow


def _inject_prompt(
    workflow: dict[str, Any], positive_prompt: str, include_mugda: bool
) -> dict[str, Any]:
    workflow = copy.deepcopy(workflow)
    lora_strength = 1.0 if include_mugda else 0.0
    for node in workflow.values():
        inputs = node.get("inputs", {})
        for key, value in inputs.items():
            if value == "__POSITIVE_PROMPT__":
                inputs[key] = positive_prompt
            elif value == "__MUGDA_LORA_STRENGTH__":
                inputs[key] = lora_strength
        # randomise seed so each run produces a different image
        if "seed" in inputs:
            inputs["seed"] = random.randint(0, 2**32 - 1)
    return workflow


async def _submit_job(endpoint_url: str, api_key: str, workflow: dict[str, Any]) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{endpoint_url}/run",
            json={"input": {"workflow": workflow}},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
        response.raise_for_status()
        job_id: str = response.json()["id"]
        return job_id


async def _poll_for_result(endpoint_url: str, api_key: str, job_id: str) -> bytes:
    deadline = asyncio.get_event_loop().time() + _POLL_TIMEOUT_SECONDS
    with logfire.span("poll_runpod_job", job_id=job_id) as span:
        async with httpx.AsyncClient() as client:
            polls = 0
            while True:
                if asyncio.get_event_loop().time() > deadline:
                    span.set_attribute("polls", polls)
                    raise TimeoutError(f"RunPod job {job_id} timed out")
                await asyncio.sleep(_POLL_INTERVAL_SECONDS)
                polls += 1
                response = await client.get(
                    f"{endpoint_url}/status/{job_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10.0,
                )
                response.raise_for_status()
                data = response.json()
                status = data.get("status")
                if status == "COMPLETED":
                    span.set_attribute("polls", polls)
                    image_b64: str = data["output"]["images"][0]
                    return base64.b64decode(image_b64)
                if status in ("FAILED", "CANCELLED"):
                    span.set_attribute("polls", polls)
                    raise RuntimeError(
                        f"RunPod job {job_id} ended with status {status}"
                    )


async def generate_image(
    description: str,
    include_mugda: bool,
    outfit_description: str = "",
) -> bytes:
    endpoint_url = os.environ["RUNPOD_ENDPOINT_URL"]
    api_key = os.environ["RUNPOD_API_KEY"]

    with logfire.span(
        "generate_image",
        include_mugda=include_mugda,
        has_outfit=bool(outfit_description),
    ) as span:
        positive_prompt = await _enhance_prompt(
            description, include_mugda, outfit_description
        )
        span.set_attribute("prompt", positive_prompt)
        logger.info("Enhanced prompt: %s", positive_prompt)

        workflow = _load_workflow()
        workflow = _inject_prompt(workflow, positive_prompt, include_mugda)

        job_id = await _submit_job(endpoint_url, api_key, workflow)
        span.set_attribute("job_id", job_id)
        logger.info("RunPod job submitted: %s", job_id)

        image_bytes = await _poll_for_result(endpoint_url, api_key, job_id)
        span.set_attribute("image_bytes", len(image_bytes))
        logger.info("RunPod job %s completed (%d bytes)", job_id, len(image_bytes))
        return image_bytes
