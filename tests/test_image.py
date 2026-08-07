import base64
from unittest.mock import AsyncMock, MagicMock, patch

from livingbot.image import (
    _enhance_prompt,
    _reference_images,
    generate_image,
)
from livingbot.prompts import IMAGE_STYLE_PREFIX, MUGDA_IMAGE_IDENTITY

# ---------------------------------------------------------------------------
# _enhance_prompt
# ---------------------------------------------------------------------------


def _make_enhancer_agent(output: str) -> MagicMock:
    agent = MagicMock()
    agent.run = AsyncMock(return_value=MagicMock(output=output))
    return agent


@patch("livingbot.image._build_enhancer_agent")
async def test_enhance_prompt_without_mugda_sends_only_description(
    mock_build_agent: MagicMock,
) -> None:
    agent = _make_enhancer_agent("a scene")
    mock_build_agent.return_value = agent

    await _enhance_prompt(
        "rainy street at night", include_mugda=False, outfit_description=""
    )

    user_content = agent.run.call_args.args[0]
    assert "rainy street at night" in user_content
    assert "Mugda" not in user_content


@patch("livingbot.image._build_enhancer_agent")
async def test_enhance_prompt_with_mugda_includes_mugda_in_message(
    mock_build_agent: MagicMock,
) -> None:
    agent = _make_enhancer_agent("a scene")
    mock_build_agent.return_value = agent

    await _enhance_prompt("at the gym", include_mugda=True, outfit_description="")

    user_content = agent.run.call_args.args[0]
    assert "Mugda" in user_content


@patch("livingbot.image._build_enhancer_agent")
async def test_enhance_prompt_with_outfit_includes_outfit_in_message(
    mock_build_agent: MagicMock,
) -> None:
    agent = _make_enhancer_agent("a scene")
    mock_build_agent.return_value = agent

    await _enhance_prompt(
        "at the gym",
        include_mugda=True,
        outfit_description="black sports bra, grey leggings",
    )

    user_content = agent.run.call_args.args[0]
    assert "black sports bra, grey leggings" in user_content


@patch("livingbot.image._build_enhancer_agent")
async def test_enhance_prompt_without_mugda_ignores_outfit_description(
    mock_build_agent: MagicMock,
) -> None:
    agent = _make_enhancer_agent("a scene")
    mock_build_agent.return_value = agent

    await _enhance_prompt(
        "forest path", include_mugda=False, outfit_description="red dress"
    )

    user_content = agent.run.call_args.args[0]
    assert "red dress" not in user_content


@patch("livingbot.image._build_enhancer_agent")
async def test_enhance_prompt_returns_model_content(
    mock_build_agent: MagicMock,
) -> None:
    mock_build_agent.return_value = _make_enhancer_agent("a vivid ghibli scene")

    result = await _enhance_prompt(
        "beach sunset", include_mugda=False, outfit_description=""
    )

    assert result == "a vivid ghibli scene"


@patch("livingbot.image._build_enhancer_agent")
async def test_enhance_prompt_when_model_returns_empty_output_falls_back_to_description(
    mock_build_agent: MagicMock,
) -> None:
    mock_build_agent.return_value = _make_enhancer_agent("")

    result = await _enhance_prompt(
        "beach sunset", include_mugda=False, outfit_description=""
    )

    assert result == "beach sunset"


# ---------------------------------------------------------------------------
# _reference_images
# ---------------------------------------------------------------------------


@patch("livingbot.image.config.MUGDA_REFERENCE_IMAGE_PATHS")
def test_reference_images_returns_base64_data_uri_per_configured_path(
    mock_paths: MagicMock, tmp_path
) -> None:
    image_path = tmp_path / "ref.png"
    image_path.write_bytes(b"fake-png-bytes")
    mock_paths.__iter__.return_value = iter([image_path])

    result = _reference_images()

    expected = f"data:image/png;base64,{base64.b64encode(b'fake-png-bytes').decode()}"
    assert result == [expected]


# ---------------------------------------------------------------------------
# generate_image
# ---------------------------------------------------------------------------

SERVICE_URL = "http://image-service:8000"


def _service_client(response_json: dict) -> AsyncMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = response_json

    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def _service_response(image_bytes: bytes = b"image-bytes") -> dict:
    return {"image_base64": base64.b64encode(image_bytes).decode(), "cost": 0.02}


@patch.dict("os.environ", {"IMAGE_SERVICE_URL": SERVICE_URL})
@patch("livingbot.image.httpx.AsyncClient")
@patch("livingbot.image._reference_images", return_value=["data:image/png;base64,AAAA"])
@patch("livingbot.image._enhance_prompt", new_callable=AsyncMock)
async def test_generate_image_with_mugda_posts_to_reference_endpoint(
    mock_enhance: AsyncMock,
    mock_reference_images: MagicMock,
    mock_httpx_cls: MagicMock,
) -> None:
    mock_enhance.return_value = "a sunny gym scene"
    client = _service_client(_service_response())
    mock_httpx_cls.return_value = client

    await generate_image("at the gym", include_mugda=True)

    assert client.post.call_args.args[0] == f"{SERVICE_URL}/generate-with-reference"


@patch.dict("os.environ", {"IMAGE_SERVICE_URL": SERVICE_URL})
@patch("livingbot.image.httpx.AsyncClient")
@patch("livingbot.image._reference_images", return_value=["data:image/png;base64,AAAA"])
@patch("livingbot.image._enhance_prompt", new_callable=AsyncMock)
async def test_generate_image_with_mugda_sends_reference_images(
    mock_enhance: AsyncMock,
    mock_reference_images: MagicMock,
    mock_httpx_cls: MagicMock,
) -> None:
    mock_enhance.return_value = "a sunny gym scene"
    client = _service_client(_service_response())
    mock_httpx_cls.return_value = client

    await generate_image("at the gym", include_mugda=True)

    payload = client.post.call_args.kwargs["json"]
    assert payload["reference_images"] == ["data:image/png;base64,AAAA"]


@patch.dict("os.environ", {"IMAGE_SERVICE_URL": SERVICE_URL})
@patch("livingbot.image.httpx.AsyncClient")
@patch("livingbot.image._reference_images", return_value=["data:image/png;base64,AAAA"])
@patch("livingbot.image._enhance_prompt", new_callable=AsyncMock)
async def test_generate_image_with_mugda_prefixes_style_and_identity_to_scene(
    mock_enhance: AsyncMock,
    mock_reference_images: MagicMock,
    mock_httpx_cls: MagicMock,
) -> None:
    mock_enhance.return_value = "a sunny gym scene"
    client = _service_client(_service_response())
    mock_httpx_cls.return_value = client

    await generate_image("at the gym", include_mugda=True)

    prompt = client.post.call_args.kwargs["json"]["prompt"]
    assert prompt == (IMAGE_STYLE_PREFIX + MUGDA_IMAGE_IDENTITY + "a sunny gym scene")


@patch.dict("os.environ", {"IMAGE_SERVICE_URL": SERVICE_URL})
@patch("livingbot.image.httpx.AsyncClient")
@patch("livingbot.image._enhance_prompt", new_callable=AsyncMock)
async def test_generate_image_without_mugda_posts_to_generate_endpoint(
    mock_enhance: AsyncMock,
    mock_httpx_cls: MagicMock,
) -> None:
    mock_enhance.return_value = "an empty park path"
    client = _service_client(_service_response())
    mock_httpx_cls.return_value = client

    await generate_image("a quiet park", include_mugda=False)

    assert client.post.call_args.args[0] == f"{SERVICE_URL}/generate"


@patch.dict("os.environ", {"IMAGE_SERVICE_URL": SERVICE_URL})
@patch("livingbot.image.httpx.AsyncClient")
@patch("livingbot.image._enhance_prompt", new_callable=AsyncMock)
async def test_generate_image_without_mugda_omits_identity_clause(
    mock_enhance: AsyncMock,
    mock_httpx_cls: MagicMock,
) -> None:
    mock_enhance.return_value = "an empty park path"
    client = _service_client(_service_response())
    mock_httpx_cls.return_value = client

    await generate_image("a quiet park", include_mugda=False)

    prompt = client.post.call_args.kwargs["json"]["prompt"]
    assert prompt == IMAGE_STYLE_PREFIX + "an empty park path"


@patch.dict("os.environ", {"IMAGE_SERVICE_URL": SERVICE_URL})
@patch("livingbot.image.httpx.AsyncClient")
@patch("livingbot.image._enhance_prompt", new_callable=AsyncMock)
async def test_generate_image_returns_decoded_image_bytes(
    mock_enhance: AsyncMock,
    mock_httpx_cls: MagicMock,
) -> None:
    mock_enhance.return_value = "a scene"
    mock_httpx_cls.return_value = _service_client(
        _service_response(b"final-image-bytes")
    )

    result = await generate_image("a quiet park", include_mugda=False)

    assert result == b"final-image-bytes"
