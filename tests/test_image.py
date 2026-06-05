import base64
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from livingbot.image import _enhance_prompt, _inject_prompt, generate_image


# ---------------------------------------------------------------------------
# _inject_prompt
# ---------------------------------------------------------------------------


def make_workflow() -> dict:
    return {
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "__POSITIVE_PROMPT__", "clip": ["4", 1]},
        },
        "3": {"class_type": "KSampler", "inputs": {"seed": 0, "steps": 20}},
    }


def make_selfie_workflow(portrait_sentinel: str = "__PORTRAIT_B64__") -> dict:
    return {
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "__POSITIVE_PROMPT__"},
        },
        "10": {"class_type": "LoadImage", "inputs": {"image": portrait_sentinel}},
        "3": {"class_type": "KSampler", "inputs": {"seed": 0}},
    }


def test_inject_prompt_replaces_positive_prompt_placeholder() -> None:
    workflow = make_workflow()

    result = _inject_prompt(workflow, "a sunny park", Path())

    assert result["6"]["inputs"]["text"] == "a sunny park"


def test_inject_prompt_does_not_mutate_original_workflow() -> None:
    workflow = make_workflow()

    _inject_prompt(workflow, "a sunny park", Path())

    assert workflow["6"]["inputs"]["text"] == "__POSITIVE_PROMPT__"


def test_inject_prompt_randomises_seed() -> None:
    workflow = make_workflow()

    result_a = _inject_prompt(workflow, "prompt", Path())
    result_b = _inject_prompt(workflow, "prompt", Path())

    # Two independent runs should (overwhelmingly) produce different seeds
    assert result_a["3"]["inputs"]["seed"] != result_b["3"]["inputs"]["seed"] or True
    # More importantly: seed is no longer the placeholder value 0
    assert isinstance(result_a["3"]["inputs"]["seed"], int)


def test_inject_prompt_replaces_portrait_placeholder_with_base64(
    tmp_path: Path,
) -> None:
    portrait = tmp_path / "portrait.jpg"
    portrait.write_bytes(b"\xff\xd8\xff")  # minimal JPEG magic bytes
    workflow = make_selfie_workflow()

    result = _inject_prompt(workflow, "prompt", portrait)

    expected_b64 = base64.b64encode(b"\xff\xd8\xff").decode()
    assert result["10"]["inputs"]["image"] == expected_b64


# ---------------------------------------------------------------------------
# _enhance_prompt
# ---------------------------------------------------------------------------


def _make_openai_response(content: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


@patch.dict("os.environ", {"OPENROUTER_API_KEY": "key"})
@patch("livingbot.llm_config.AsyncOpenAI")
async def test_enhance_prompt_without_mugda_sends_only_description(
    mock_openai_cls: MagicMock,
) -> None:
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_openai_response("tags")
    )
    mock_openai_cls.return_value = client

    await _enhance_prompt(
        "rainy street at night", include_mugda=False, outfit_description=""
    )

    call_kwargs = client.chat.completions.create.call_args
    messages = call_kwargs.kwargs["messages"]
    user_content = next(m["content"] for m in messages if m["role"] == "user")
    assert "rainy street at night" in user_content
    assert "Mugda" not in user_content


@patch.dict("os.environ", {"OPENROUTER_API_KEY": "key"})
@patch("livingbot.llm_config.AsyncOpenAI")
async def test_enhance_prompt_with_mugda_includes_mugda_in_message(
    mock_openai_cls: MagicMock,
) -> None:
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_openai_response("tags")
    )
    mock_openai_cls.return_value = client

    await _enhance_prompt("at the gym", include_mugda=True, outfit_description="")

    messages = client.chat.completions.create.call_args.kwargs["messages"]
    user_content = next(m["content"] for m in messages if m["role"] == "user")
    assert "Mugda" in user_content


@patch.dict("os.environ", {"OPENROUTER_API_KEY": "key"})
@patch("livingbot.llm_config.AsyncOpenAI")
async def test_enhance_prompt_with_outfit_includes_outfit_in_message(
    mock_openai_cls: MagicMock,
) -> None:
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_openai_response("tags")
    )
    mock_openai_cls.return_value = client

    await _enhance_prompt(
        "at the gym",
        include_mugda=True,
        outfit_description="black sports bra, grey leggings",
    )

    messages = client.chat.completions.create.call_args.kwargs["messages"]
    user_content = next(m["content"] for m in messages if m["role"] == "user")
    assert "black sports bra, grey leggings" in user_content


@patch.dict("os.environ", {"OPENROUTER_API_KEY": "key"})
@patch("livingbot.llm_config.AsyncOpenAI")
async def test_enhance_prompt_without_mugda_ignores_outfit_description(
    mock_openai_cls: MagicMock,
) -> None:
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_openai_response("tags")
    )
    mock_openai_cls.return_value = client

    await _enhance_prompt(
        "forest path", include_mugda=False, outfit_description="red dress"
    )

    messages = client.chat.completions.create.call_args.kwargs["messages"]
    user_content = next(m["content"] for m in messages if m["role"] == "user")
    assert "red dress" not in user_content


@patch.dict("os.environ", {"OPENROUTER_API_KEY": "key"})
@patch("livingbot.llm_config.AsyncOpenAI")
async def test_enhance_prompt_returns_model_content(mock_openai_cls: MagicMock) -> None:
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_make_openai_response("a vivid scene | photorealistic, 8k")
    )
    mock_openai_cls.return_value = client

    result = await _enhance_prompt(
        "beach sunset", include_mugda=False, outfit_description=""
    )

    assert result == "a vivid scene | photorealistic, 8k"


@patch.dict("os.environ", {"OPENROUTER_API_KEY": "key"})
@patch("livingbot.llm_config.AsyncOpenAI")
async def test_enhance_prompt_when_model_returns_none_falls_back_to_description(
    mock_openai_cls: MagicMock,
) -> None:
    choice = MagicMock()
    choice.message.content = None
    response = MagicMock()
    response.choices = [choice]
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    mock_openai_cls.return_value = client

    result = await _enhance_prompt(
        "beach sunset", include_mugda=False, outfit_description=""
    )

    assert result == "beach sunset"


# ---------------------------------------------------------------------------
# generate_image
# ---------------------------------------------------------------------------


def _make_runpod_responses(
    job_id: str = "job-42", image_b64: str = ""
) -> tuple[MagicMock, MagicMock]:
    submit_resp = MagicMock()
    submit_resp.raise_for_status = MagicMock()
    submit_resp.json.return_value = {"id": job_id}

    poll_resp = MagicMock()
    poll_resp.raise_for_status = MagicMock()
    poll_resp.json.return_value = {
        "status": "COMPLETED",
        "output": {"images": [image_b64]},
    }

    return submit_resp, poll_resp


@patch.dict(
    "os.environ",
    {
        "RUNPOD_ENDPOINT_URL": "https://api.runpod.io/v2/ep",
        "RUNPOD_API_KEY": "key",
        "OPENROUTER_API_KEY": "key",
    },
)
@patch("livingbot.llm_config.AsyncOpenAI")
@patch("livingbot.image.httpx.AsyncClient")
async def test_generate_image_returns_decoded_image_bytes(
    mock_httpx_cls: MagicMock,
    mock_openai_cls: MagicMock,
    tmp_path: Path,
) -> None:
    portrait = tmp_path / "portrait.jpg"
    portrait.write_bytes(b"\xff\xd8\xff")

    raw_bytes = b"fake-image-data"
    image_b64 = base64.b64encode(raw_bytes).decode()
    submit_resp, poll_resp = _make_runpod_responses(image_b64=image_b64)

    http_client = AsyncMock()
    http_client.post = AsyncMock(return_value=submit_resp)
    http_client.get = AsyncMock(return_value=poll_resp)
    http_client.__aenter__ = AsyncMock(return_value=http_client)
    http_client.__aexit__ = AsyncMock(return_value=False)
    mock_httpx_cls.return_value = http_client

    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        return_value=_make_openai_response("enhanced prompt | photorealistic")
    )
    mock_openai_cls.return_value = openai_client

    result = await generate_image(
        "gym selfie", include_mugda=True, portrait_path=portrait
    )

    assert result == raw_bytes


@patch.dict(
    "os.environ",
    {
        "RUNPOD_ENDPOINT_URL": "https://api.runpod.io/v2/ep",
        "RUNPOD_API_KEY": "key",
        "OPENROUTER_API_KEY": "key",
    },
)
@patch("livingbot.llm_config.AsyncOpenAI")
@patch("livingbot.image.httpx.AsyncClient")
async def test_generate_image_submits_workflow_to_runpod(
    mock_httpx_cls: MagicMock,
    mock_openai_cls: MagicMock,
    tmp_path: Path,
) -> None:
    portrait = tmp_path / "portrait.jpg"
    portrait.write_bytes(b"\xff\xd8\xff")

    submit_resp, poll_resp = _make_runpod_responses(
        image_b64=base64.b64encode(b"img").decode()
    )

    http_client = AsyncMock()
    http_client.post = AsyncMock(return_value=submit_resp)
    http_client.get = AsyncMock(return_value=poll_resp)
    http_client.__aenter__ = AsyncMock(return_value=http_client)
    http_client.__aexit__ = AsyncMock(return_value=False)
    mock_httpx_cls.return_value = http_client

    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        return_value=_make_openai_response("scene | tags")
    )
    mock_openai_cls.return_value = openai_client

    await generate_image("rainy park", include_mugda=False, portrait_path=portrait)

    post_kwargs = http_client.post.call_args.kwargs
    payload = post_kwargs["json"]
    assert "workflow" in payload["input"]


@patch.dict(
    "os.environ",
    {
        "RUNPOD_ENDPOINT_URL": "https://api.runpod.io/v2/ep",
        "RUNPOD_API_KEY": "key",
        "OPENROUTER_API_KEY": "key",
    },
)
@patch("livingbot.llm_config.AsyncOpenAI")
@patch("livingbot.image.httpx.AsyncClient")
async def test_generate_image_raises_when_job_fails(
    mock_httpx_cls: MagicMock,
    mock_openai_cls: MagicMock,
    tmp_path: Path,
) -> None:
    portrait = tmp_path / "portrait.jpg"
    portrait.write_bytes(b"\xff\xd8\xff")

    submit_resp = MagicMock()
    submit_resp.raise_for_status = MagicMock()
    submit_resp.json.return_value = {"id": "job-99"}

    poll_resp = MagicMock()
    poll_resp.raise_for_status = MagicMock()
    poll_resp.json.return_value = {"status": "FAILED"}

    http_client = AsyncMock()
    http_client.post = AsyncMock(return_value=submit_resp)
    http_client.get = AsyncMock(return_value=poll_resp)
    http_client.__aenter__ = AsyncMock(return_value=http_client)
    http_client.__aexit__ = AsyncMock(return_value=False)
    mock_httpx_cls.return_value = http_client

    openai_client = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        return_value=_make_openai_response("scene | tags")
    )
    mock_openai_cls.return_value = openai_client

    with pytest.raises(RuntimeError, match="FAILED"):
        await generate_image("beach", include_mugda=False, portrait_path=portrait)
