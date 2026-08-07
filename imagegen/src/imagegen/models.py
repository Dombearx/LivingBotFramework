from pydantic import BaseModel, ConfigDict, Field


class Lora(BaseModel):
    """A LoRA adapter layered on top of the base text-to-image model."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "path": "https://civitai.com/api/download/models/2181392",
                    "scale": 1.0,
                }
            ]
        }
    )

    path: str = Field(
        min_length=1,
        description=(
            "Publicly reachable URL that RunPod downloads the adapter weights "
            "from, such as a Civitai download link. RunPod fetches this itself, "
            "so it must be reachable from the public internet rather than from "
            "the caller."
        ),
        examples=["https://civitai.com/api/download/models/2181392"],
    )
    scale: float = Field(
        default=1.0,
        description=(
            "How strongly the adapter is applied. 1.0 is full strength; lower "
            "values blend it with the base model."
        ),
        examples=[1.0],
    )


class GenerateRequest(BaseModel):
    """Body for POST /generate."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "prompt": (
                        "Studio Ghibli style hand-painted anime illustration, "
                        "a quiet park path at dusk, warm painterly lighting"
                    ),
                    "seed": -1,
                    "loras": [],
                }
            ]
        }
    )

    prompt: str = Field(
        min_length=1,
        description=(
            "The complete prompt sent to the model. The service applies no "
            "styling, rewriting or enhancement of its own, so include every "
            "style and composition instruction here."
        ),
        examples=["a quiet park path at dusk, warm painterly lighting"],
    )
    seed: int = Field(
        default=-1,
        description=(
            "Seed for reproducible output. -1 asks RunPod for a random seed, "
            "which means repeat calls with the same prompt return different "
            "images. Pass a fixed non-negative value to make a result "
            "repeatable."
        ),
        examples=[-1],
    )
    loras: list[Lora] = Field(
        default_factory=list,
        description=(
            "Optional LoRA adapters. Supplying any switches the job to RunPod's "
            "qwen-image-t2i-lora endpoint, because the plain text-to-image "
            "endpoint rejects the field; leaving it empty uses the plain one. "
            "Expect longer jobs and a different cost when adapters are used, "
            "since RunPod downloads the weights per job."
        ),
    )


class GenerateWithReferenceRequest(BaseModel):
    """Body for POST /generate-with-reference."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "prompt": (
                        "Studio Ghibli style hand-painted anime illustration, "
                        "the same woman shown in the reference photos, sitting "
                        "on a bench in a park at dusk"
                    ),
                    "reference_images": [
                        "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD..."
                    ],
                }
            ]
        }
    )

    prompt: str = Field(
        min_length=1,
        description=(
            "The complete prompt sent to the model. Describe how the subject in "
            "the reference images should appear in the new scene. The service "
            "applies no styling or rewriting of its own."
        ),
        examples=["the woman from the reference photos, sitting on a park bench"],
    )
    reference_images: list[str] = Field(
        min_length=1,
        description=(
            "One or more reference images as base64 data URIs, formatted "
            "'data:<mime-type>;base64,<data>'. image/jpeg and image/png are "
            "known to work. The model reads these to keep the subject's "
            "identity consistent, so they should show the same subject. "
            "Encoded images are roughly a third larger than the source bytes, "
            "so keep the originals small enough for the request to stay "
            "practical."
        ),
    )


class GenerateResponse(BaseModel):
    """Successful result from either generation endpoint."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"image_base64": "iVBORw0KGgoAAAANSUhEUg...", "cost": 0.021}]
        }
    )

    image_base64: str = Field(
        description=(
            "The generated image, base64-encoded without a data URI prefix. "
            "Decode it to get the raw image bytes. The format is whatever the "
            "model produced and is not guaranteed, so detect it from the "
            "decoded bytes rather than assuming an extension."
        ),
    )
    cost: float | None = Field(
        description=(
            "What RunPod charged for the job, in USD. Null when RunPod did not "
            "report a cost, so treat it as informational rather than "
            "guaranteed."
        ),
        examples=[0.021],
    )
