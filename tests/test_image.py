import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from livingbot.image import (
    _enhance_prompt,
    _reference_images,
    _run_job,
    generate_image,
)

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
# _run_job
# ---------------------------------------------------------------------------


def _mock_response(json_data: dict) -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = json_data
    return response


async def test_run_job_returns_output_when_job_completes_immediately() -> None:
    client = AsyncMock()
    client.post = AsyncMock(
        return_value=_mock_response(
            {"id": "job-1", "status": "COMPLETED", "output": {"result": "url"}}
        )
    )

    output = await _run_job(client, "https://example.com", "key", {"prompt": "x"})

    assert output == {"result": "url"}
    client.get.assert_not_called()


@patch("livingbot.image.asyncio.sleep", new_callable=AsyncMock)
async def test_run_job_polls_status_until_completed(
    mock_sleep: AsyncMock,
) -> None:
    client = AsyncMock()
    client.post = AsyncMock(
        return_value=_mock_response({"id": "job-2", "status": "IN_QUEUE"})
    )
    client.get = AsyncMock(
        side_effect=[
            _mock_response({"id": "job-2", "status": "IN_PROGRESS"}),
            _mock_response(
                {"id": "job-2", "status": "COMPLETED", "output": {"result": "done"}}
            ),
        ]
    )

    output = await _run_job(client, "https://example.com", "key", {"prompt": "x"})

    assert output == {"result": "done"}


async def test_run_job_raises_when_job_fails() -> None:
    client = AsyncMock()
    client.post = AsyncMock(
        return_value=_mock_response({"id": "job-3", "status": "FAILED"})
    )

    with pytest.raises(RuntimeError, match="FAILED"):
        await _run_job(client, "https://example.com", "key", {"prompt": "x"})


# ---------------------------------------------------------------------------
# generate_image
# ---------------------------------------------------------------------------


def _download_client(image_bytes: bytes) -> AsyncMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.content = image_bytes

    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


@patch.dict("os.environ", {"RUNPOD_API_KEY": "key"})
@patch("livingbot.image.httpx.AsyncClient")
@patch("livingbot.image._run_job")
@patch("livingbot.image._reference_images", return_value=["data:image/png;base64,AAAA"])
@patch("livingbot.image._enhance_prompt", new_callable=AsyncMock)
async def test_generate_image_with_mugda_calls_selfie_endpoint_with_reference_images(
    mock_enhance: AsyncMock,
    mock_reference_images: MagicMock,
    mock_run_job: AsyncMock,
    mock_httpx_cls: MagicMock,
) -> None:
    mock_enhance.return_value = "a sunny gym scene"
    mock_run_job.return_value = {"result": "https://img.example/out.jpg", "cost": 0.02}
    mock_httpx_cls.return_value = _download_client(b"image-bytes")

    await generate_image("at the gym", include_mugda=True)

    call_args = mock_run_job.call_args.args
    assert call_args[1] == "https://api.runpod.ai/v2/nano-banana-edit"
    payload = call_args[3]
    assert payload["images"] == ["data:image/png;base64,AAAA"]
    assert payload["enable_safety_checker"] is False
    assert "Studio Ghibli" in payload["prompt"]
    assert "same woman shown in the reference photos" in payload["prompt"]
    assert "a sunny gym scene" in payload["prompt"]


@patch.dict("os.environ", {"RUNPOD_API_KEY": "key"})
@patch("livingbot.image.httpx.AsyncClient")
@patch("livingbot.image._run_job")
@patch("livingbot.image._enhance_prompt", new_callable=AsyncMock)
async def test_generate_image_without_mugda_calls_scenery_endpoint_without_images(
    mock_enhance: AsyncMock,
    mock_run_job: AsyncMock,
    mock_httpx_cls: MagicMock,
) -> None:
    mock_enhance.return_value = "an empty park path"
    mock_run_job.return_value = {"result": "https://img.example/out.jpg", "cost": 0.02}
    mock_httpx_cls.return_value = _download_client(b"image-bytes")

    await generate_image("a quiet park", include_mugda=False)

    call_args = mock_run_job.call_args.args
    assert call_args[1] == "https://api.runpod.ai/v2/qwen-image-t2i"
    payload = call_args[3]
    assert "images" not in payload
    assert payload["seed"] == -1
    assert payload["enable_safety_checker"] is False
    assert "same woman shown in the reference photos" not in payload["prompt"]


@patch.dict("os.environ", {"RUNPOD_API_KEY": "key"})
@patch("livingbot.image.httpx.AsyncClient")
@patch("livingbot.image._run_job")
@patch("livingbot.image._enhance_prompt", new_callable=AsyncMock)
async def test_generate_image_returns_downloaded_image_bytes(
    mock_enhance: AsyncMock,
    mock_run_job: AsyncMock,
    mock_httpx_cls: MagicMock,
) -> None:
    mock_enhance.return_value = "a scene"
    mock_run_job.return_value = {"result": "https://img.example/out.jpg", "cost": 0.02}
    mock_httpx_cls.return_value = _download_client(b"final-image-bytes")

    result = await generate_image("a quiet park", include_mugda=False)

    assert result == b"final-image-bytes"
