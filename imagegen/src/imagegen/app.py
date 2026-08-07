import base64
import logging
import os
from typing import Any

import logfire
import uvicorn
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from imagegen import runpod
from imagegen.models import (
    GenerateRequest,
    GenerateResponse,
    GenerateWithReferenceRequest,
)
from imagegen.observability import configure_logfire

logger = logging.getLogger(__name__)

HOST = "0.0.0.0"
DEFAULT_PORT = 8000

API_DESCRIPTION = """
Turns a prompt into an image by running a RunPod job and returning the result.

The service is deliberately unopinionated: it applies no styling, rewriting or
prompt enhancement of its own, so callers own the full prompt text and any
persona or style wording it needs. That keeps it reusable by any service rather
than tied to one caller's look.

### Choosing an endpoint

- `POST /generate` renders a prompt with no subject to keep consistent, such as
  scenery, objects or abstract scenes. Optionally accepts LoRA adapters.
- `POST /generate-with-reference` renders a prompt alongside reference images of
  a subject, and keeps that subject's identity consistent with them. Use it for
  anything where a specific person or character must look the same across
  images. It does not accept LoRA adapters.

### Calling it

There is no authentication; the service is expected to run on a private
network. Requests are JSON in and JSON out, and images come back
base64-encoded.

Generation is synchronous and slow: a call blocks until the image is ready and
can take several minutes, so use a client timeout of at least 360 seconds. There
is no job handle, callback or polling API to resume from — a dropped connection
loses the result while still costing money, since the RunPod job runs
regardless.
"""

UPSTREAM_FAILURE_RESPONSE: dict[int | str, dict[str, Any]] = {
    500: {
        "description": (
            "The RunPod job failed or timed out, the generated image could not "
            "be downloaded, or RUNPOD_API_KEY is not configured on the service. "
            "The body is FastAPI's default error payload and carries no "
            "machine-readable failure code, so treat any 500 as a generic "
            "upstream failure and retry or give up rather than branching on it."
        )
    }
}

app = FastAPI(
    title="Image generation service",
    version="0.1.0",
    description=API_DESCRIPTION,
)


def _api_key() -> str:
    return os.environ["RUNPOD_API_KEY"]


def _response(image_bytes: bytes, cost: float | None) -> GenerateResponse:
    return GenerateResponse(
        image_base64=base64.b64encode(image_bytes).decode(), cost=cost
    )


@app.get(
    "/health",
    summary="Check that the service is reachable",
    response_description="The literal text 'ok'.",
    responses={200: {"content": {"text/plain": {"example": "ok"}}}},
)
def health() -> PlainTextResponse:
    """Report that the service is up.

    Returns 200 as long as the process is serving. It does not call RunPod, so a
    healthy response says nothing about whether image generation currently works
    or whether `RUNPOD_API_KEY` is set. Safe to poll as a readiness check.
    """
    return PlainTextResponse("ok")


@app.post(
    "/generate",
    summary="Generate an image from a text prompt",
    response_description=(
        "The generated image, base64-encoded, with the cost RunPod reported."
    ),
    responses=UPSTREAM_FAILURE_RESPONSE,
)
async def generate(request: GenerateRequest) -> GenerateResponse:
    """Render a prompt as a new image, with nothing to keep consistent.

    Runs RunPod's `qwen-image-t2i` model. Use this for scenery, objects and any
    scene with no specific subject whose appearance has to match other images.

    Supplying `loras` switches the job to `qwen-image-t2i-lora`, since the plain
    endpoint rejects the field. Everything else about the request is unchanged.

    `seed` defaults to -1, meaning RunPod picks one at random and repeated calls
    with an identical body return different images. Pass a fixed non-negative
    seed when a result needs to be reproducible.
    """
    payload: dict[str, Any] = {
        "prompt": request.prompt,
        "seed": request.seed,
        "enable_safety_checker": False,
    }
    if request.loras:
        payload["loras"] = [lora.model_dump() for lora in request.loras]
        base_url = runpod.TEXT_TO_IMAGE_LORA_ENDPOINT
    else:
        base_url = runpod.TEXT_TO_IMAGE_ENDPOINT

    with logfire.span(
        "generate", prompt=request.prompt, lora_count=len(request.loras)
    ) as span:
        image_bytes, cost = await runpod.generate(base_url, _api_key(), payload)
        span.set_attribute("cost", cost)
        span.set_attribute("image_bytes", len(image_bytes))
    return _response(image_bytes, cost)


@app.post(
    "/generate-with-reference",
    summary="Generate an image guided by reference images of a subject",
    response_description=(
        "The generated image, base64-encoded, with the cost RunPod reported."
    ),
    responses=UPSTREAM_FAILURE_RESPONSE,
)
async def generate_with_reference(
    request: GenerateWithReferenceRequest,
) -> GenerateResponse:
    """Render a prompt while keeping a subject consistent with reference images.

    Runs RunPod's `nano-banana-edit` model, which reads the reference images to
    preserve the subject's face, build and identity in the new scene. Use this
    whenever a specific person or character has to look the same across images;
    it is what makes a series of pictures recognisably the same subject rather
    than a new one each time.

    Reference images are base64 data URIs sent inline in the request body, so
    the service stores nothing between calls and holds no subject of its own.
    Callers supply their own references every time.

    This endpoint takes no `loras` and no `seed`: the underlying model is a
    hosted Gemini image model that accepts only a prompt and images. Sending
    either field is silently ignored rather than rejected.
    """
    payload = {
        "prompt": request.prompt,
        "images": request.reference_images,
        "enable_safety_checker": False,
    }
    with logfire.span(
        "generate_with_reference",
        prompt=request.prompt,
        reference_count=len(request.reference_images),
    ) as span:
        image_bytes, cost = await runpod.generate(
            runpod.REFERENCE_ENDPOINT, _api_key(), payload
        )
        span.set_attribute("cost", cost)
        span.set_attribute("image_bytes", len(image_bytes))
    return _response(image_bytes, cost)


def run() -> None:
    configure_logfire(app)
    port = int(os.environ.get("IMAGE_SERVICE_PORT", DEFAULT_PORT))
    uvicorn.run(app, host=HOST, port=port)
