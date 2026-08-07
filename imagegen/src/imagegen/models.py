from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    seed: int = -1


class GenerateWithReferenceRequest(BaseModel):
    prompt: str = Field(min_length=1)
    reference_images: list[str] = Field(min_length=1)


class GenerateResponse(BaseModel):
    image_base64: str
    cost: float | None
