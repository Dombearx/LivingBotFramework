from pydantic import BaseModel, Field


class Lora(BaseModel):
    path: str = Field(min_length=1)
    scale: float = 1.0


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    seed: int = -1
    loras: list[Lora] = Field(default_factory=list)


class GenerateWithReferenceRequest(BaseModel):
    prompt: str = Field(min_length=1)
    reference_images: list[str] = Field(min_length=1)


class GenerateResponse(BaseModel):
    image_base64: str
    cost: float | None
