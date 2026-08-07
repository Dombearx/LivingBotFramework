import base64
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from imagegen import runpod
from imagegen.app import app

client = TestClient(app)


@patch.dict("os.environ", {"RUNPOD_API_KEY": "key"})
@patch(
    "imagegen.app.runpod.generate",
    new_callable=AsyncMock,
    return_value=(b"image-bytes", 0.02),
)
def test_generate_sends_prompt_and_seed_to_text_to_image_endpoint(
    mock_generate: AsyncMock,
) -> None:
    client.post("/generate", json={"prompt": "a quiet park", "seed": 7})

    base_url, _, payload = mock_generate.call_args.args
    assert base_url == runpod.TEXT_TO_IMAGE_ENDPOINT
    assert payload == {
        "prompt": "a quiet park",
        "seed": 7,
        "enable_safety_checker": False,
    }


@patch.dict("os.environ", {"RUNPOD_API_KEY": "key"})
@patch(
    "imagegen.app.runpod.generate",
    new_callable=AsyncMock,
    return_value=(b"image-bytes", 0.02),
)
def test_generate_without_seed_defaults_to_random_seed(
    mock_generate: AsyncMock,
) -> None:
    client.post("/generate", json={"prompt": "a quiet park"})

    payload = mock_generate.call_args.args[2]
    assert payload["seed"] == -1


@patch.dict("os.environ", {"RUNPOD_API_KEY": "key"})
@patch(
    "imagegen.app.runpod.generate",
    new_callable=AsyncMock,
    return_value=(b"image-bytes", 0.02),
)
def test_generate_with_reference_sends_images_to_reference_endpoint(
    mock_generate: AsyncMock,
) -> None:
    client.post(
        "/generate-with-reference",
        json={"prompt": "at the gym", "reference_images": ["data:image/png;base64,AA"]},
    )

    base_url, _, payload = mock_generate.call_args.args
    assert base_url == runpod.REFERENCE_ENDPOINT
    assert payload == {
        "prompt": "at the gym",
        "images": ["data:image/png;base64,AA"],
        "enable_safety_checker": False,
    }


@patch.dict("os.environ", {"RUNPOD_API_KEY": "key"})
@patch(
    "imagegen.app.runpod.generate",
    new_callable=AsyncMock,
    return_value=(b"image-bytes", 0.02),
)
def test_generate_returns_base64_encoded_image_and_cost(
    mock_generate: AsyncMock,
) -> None:
    response = client.post("/generate", json={"prompt": "a quiet park"})

    assert response.json() == {
        "image_base64": base64.b64encode(b"image-bytes").decode(),
        "cost": 0.02,
    }


def test_generate_with_reference_rejects_empty_reference_image_list() -> None:
    response = client.post(
        "/generate-with-reference",
        json={"prompt": "at the gym", "reference_images": []},
    )

    assert response.status_code == 422


@patch.dict("os.environ", {"RUNPOD_API_KEY": "key"})
@patch(
    "imagegen.app.runpod.generate",
    new_callable=AsyncMock,
    return_value=(b"image-bytes", 0.02),
)
def test_generate_with_loras_routes_to_lora_endpoint(
    mock_generate: AsyncMock,
) -> None:
    client.post(
        "/generate",
        json={
            "prompt": "a quiet park",
            "loras": [{"path": "https://civitai.example/ghibli", "scale": 0.8}],
        },
    )

    assert mock_generate.call_args.args[0] == runpod.TEXT_TO_IMAGE_LORA_ENDPOINT


@patch.dict("os.environ", {"RUNPOD_API_KEY": "key"})
@patch(
    "imagegen.app.runpod.generate",
    new_callable=AsyncMock,
    return_value=(b"image-bytes", 0.02),
)
def test_generate_with_loras_forwards_path_and_scale(
    mock_generate: AsyncMock,
) -> None:
    client.post(
        "/generate",
        json={
            "prompt": "a quiet park",
            "loras": [{"path": "https://civitai.example/ghibli", "scale": 0.8}],
        },
    )

    payload = mock_generate.call_args.args[2]
    assert payload["loras"] == [
        {"path": "https://civitai.example/ghibli", "scale": 0.8}
    ]


@patch.dict("os.environ", {"RUNPOD_API_KEY": "key"})
@patch(
    "imagegen.app.runpod.generate",
    new_callable=AsyncMock,
    return_value=(b"image-bytes", 0.02),
)
def test_generate_with_lora_omitting_scale_defaults_to_full_strength(
    mock_generate: AsyncMock,
) -> None:
    client.post(
        "/generate",
        json={
            "prompt": "a quiet park",
            "loras": [{"path": "https://civitai.example/ghibli"}],
        },
    )

    payload = mock_generate.call_args.args[2]
    assert payload["loras"] == [
        {"path": "https://civitai.example/ghibli", "scale": 1.0}
    ]


@patch.dict("os.environ", {"RUNPOD_API_KEY": "key"})
@patch(
    "imagegen.app.runpod.generate",
    new_callable=AsyncMock,
    return_value=(b"image-bytes", 0.02),
)
def test_generate_without_loras_omits_them_from_the_payload(
    mock_generate: AsyncMock,
) -> None:
    client.post("/generate", json={"prompt": "a quiet park"})

    payload = mock_generate.call_args.args[2]
    assert "loras" not in payload
