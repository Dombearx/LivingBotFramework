import base64
import logging
import os

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

app = FastAPI(title="Image generation service")


def _api_key() -> str:
    return os.environ["RUNPOD_API_KEY"]


def _response(image_bytes: bytes, cost: float | None) -> GenerateResponse:
    return GenerateResponse(
        image_base64=base64.b64encode(image_bytes).decode(), cost=cost
    )


@app.get("/health", response_class=PlainTextResponse)
def health() -> PlainTextResponse:
    return PlainTextResponse("ok")


@app.post("/generate")
async def generate(request: GenerateRequest) -> GenerateResponse:
    payload = {
        "prompt": request.prompt,
        "seed": request.seed,
        "enable_safety_checker": False,
    }
    with logfire.span("generate", prompt=request.prompt) as span:
        image_bytes, cost = await runpod.generate(
            runpod.TEXT_TO_IMAGE_ENDPOINT, _api_key(), payload
        )
        span.set_attribute("cost", cost)
        span.set_attribute("image_bytes", len(image_bytes))
    return _response(image_bytes, cost)


@app.post("/generate-with-reference")
async def generate_with_reference(
    request: GenerateWithReferenceRequest,
) -> GenerateResponse:
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
    configure_logfire()
    port = int(os.environ.get("IMAGE_SERVICE_PORT", DEFAULT_PORT))
    uvicorn.run(app, host=HOST, port=port)
