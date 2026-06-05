import asyncio
import base64
import copy
import json
import logging
import os
import random
from importlib.resources import files
from pathlib import Path

import httpx

from livingbot import llm_config

logger = logging.getLogger(__name__)

_PROMPT_ENHANCER_SYSTEM = (
    "You are a prompt engineer for a photorealistic image generation model. "
    "Given a scene description, write an image generation prompt in two parts separated by ' | ':\n"
    "1. A vivid, detailed paragraph describing the scene — the setting, atmosphere, lighting, "
    "mood, actions, and any people present including their exact appearance and clothing. "
    "Write it as a direct scene description, not as instructions.\n"
    "2. A comma-separated list of quality and style tags "
    "(e.g. 'photorealistic, 8k, cinematic lighting, sharp focus, Canon EOS R5').\n"
    "Output only these two parts joined by ' | ' — nothing else."
)

_POLL_INTERVAL_SECONDS = 3.0
_POLL_TIMEOUT_SECONDS = 120.0


async def _enhance_prompt(
    description: str,
    include_mugda: bool,
    outfit_description: str,
) -> str:
    parts: list[str] = [description]
    if include_mugda:
        mugda = (
            "Mugda, a young Polish woman, is present and clearly visible in the scene."
        )
        if outfit_description:
            mugda += f" She is wearing: {outfit_description}."
        parts.append(mugda)
    user_message = " ".join(parts)
    client = llm_config.build_openai_client()
    response = await client.chat.completions.create(
        model=llm_config.PROMPT_ENHANCER_MODEL,
        messages=[
            {"role": "system", "content": _PROMPT_ENHANCER_SYSTEM},
            {"role": "user", "content": user_message},
        ],
        max_tokens=400,
        temperature=0.7,
    )
    return response.choices[0].message.content or description


def _load_workflow(include_mugda: bool) -> dict:
    name = "selfie.json" if include_mugda else "photo.json"
    workflow_text = files("livingbot.workflows").joinpath(name).read_text()
    return json.loads(workflow_text)


def _inject_prompt(workflow: dict, positive_prompt: str, portrait_path: Path) -> dict:
    workflow = copy.deepcopy(workflow)
    for node in workflow.values():
        inputs = node.get("inputs", {})
        for key, value in inputs.items():
            if value == "__POSITIVE_PROMPT__":
                inputs[key] = positive_prompt
            elif value == "__PORTRAIT_B64__":
                portrait_b64 = base64.b64encode(portrait_path.read_bytes()).decode()
                inputs[key] = portrait_b64
        # randomise seed so each run produces a different image
        if "seed" in inputs:
            inputs["seed"] = random.randint(0, 2**32 - 1)
    return workflow


async def _submit_job(endpoint_url: str, api_key: str, workflow: dict) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{endpoint_url}/run",
            json={"input": {"workflow": workflow}},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()["id"]


async def _poll_for_result(endpoint_url: str, api_key: str, job_id: str) -> bytes:
    deadline = asyncio.get_event_loop().time() + _POLL_TIMEOUT_SECONDS
    async with httpx.AsyncClient() as client:
        while True:
            if asyncio.get_event_loop().time() > deadline:
                raise TimeoutError(f"RunPod job {job_id} timed out")
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            response = await client.get(
                f"{endpoint_url}/status/{job_id}",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            status = data.get("status")
            if status == "COMPLETED":
                image_b64: str = data["output"]["images"][0]
                return base64.b64decode(image_b64)
            if status in ("FAILED", "CANCELLED"):
                raise RuntimeError(f"RunPod job {job_id} ended with status {status}")


async def generate_image(
    description: str,
    include_mugda: bool,
    portrait_path: Path,
    outfit_description: str = "",
) -> bytes:
    endpoint_url = os.environ["RUNPOD_ENDPOINT_URL"]
    api_key = os.environ["RUNPOD_API_KEY"]

    logger.info("Enhancing prompt (include_mugda=%s)", include_mugda)
    positive_prompt = await _enhance_prompt(
        description, include_mugda, outfit_description
    )
    logger.info("Enhanced prompt: %s", positive_prompt)

    workflow = _load_workflow(include_mugda)
    workflow = _inject_prompt(workflow, positive_prompt, portrait_path)

    job_id = await _submit_job(endpoint_url, api_key, workflow)
    logger.info("RunPod job submitted: %s", job_id)

    image_bytes = await _poll_for_result(endpoint_url, api_key, job_id)
    logger.info("RunPod job %s completed (%d bytes)", job_id, len(image_bytes))
    return image_bytes
