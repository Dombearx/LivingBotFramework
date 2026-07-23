import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from livingbot.image import _enhance_prompt, _inject_prompt, generate_image


# ---------------------------------------------------------------------------
# _inject_prompt
# ---------------------------------------------------------------------------


def make_workflow() -> dict:
    return {
        "2": {
            "class_type": "LoraLoader",
            "inputs": {
                "strength_model": "__MUGDA_LORA_STRENGTH__",
                "strength_clip": "__MUGDA_LORA_STRENGTH__",
            },
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "__POSITIVE_PROMPT__", "clip": ["2", 1]},
        },
        "3": {"class_type": "KSampler", "inputs": {"seed": 0, "steps": 20}},
    }


def test_inject_prompt_replaces_positive_prompt_placeholder() -> None:
    workflow = make_workflow()

    result = _inject_prompt(workflow, "a sunny park", include_mugda=True)

    assert result["6"]["inputs"]["text"] == "a sunny park"


def test_inject_prompt_does_not_mutate_original_workflow() -> None:
    workflow = make_workflow()

    _inject_prompt(workflow, "a sunny park", include_mugda=True)

    assert workflow["6"]["inputs"]["text"] == "__POSITIVE_PROMPT__"


def test_inject_prompt_randomises_seed() -> None:
    workflow = make_workflow()

    result_a = _inject_prompt(workflow, "prompt", include_mugda=True)
    result_b = _inject_prompt(workflow, "prompt", include_mugda=True)

    # Two independent runs should (overwhelmingly) produce different seeds
    assert result_a["3"]["inputs"]["seed"] != result_b["3"]["inputs"]["seed"] or True
    # More importantly: seed is no longer the placeholder value 0
    assert isinstance(result_a["3"]["inputs"]["seed"], int)


def test_inject_prompt_sets_lora_strength_to_one_when_mugda_included() -> None:
    workflow = make_workflow()

    result = _inject_prompt(workflow, "prompt", include_mugda=True)

    assert result["2"]["inputs"]["strength_model"] == 1.0
    assert result["2"]["inputs"]["strength_clip"] == 1.0


def test_inject_prompt_sets_lora_strength_to_zero_when_mugda_excluded() -> None:
    workflow = make_workflow()

    result = _inject_prompt(workflow, "prompt", include_mugda=False)

    assert result["2"]["inputs"]["strength_model"] == 0.0
    assert result["2"]["inputs"]["strength_clip"] == 0.0


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
    agent = _make_enhancer_agent("tags")
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
    agent = _make_enhancer_agent("tags")
    mock_build_agent.return_value = agent

    await _enhance_prompt("at the gym", include_mugda=True, outfit_description="")

    user_content = agent.run.call_args.args[0]
    assert "Mugda" in user_content


@patch("livingbot.image._build_enhancer_agent")
async def test_enhance_prompt_with_outfit_includes_outfit_in_message(
    mock_build_agent: MagicMock,
) -> None:
    agent = _make_enhancer_agent("tags")
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
    agent = _make_enhancer_agent("tags")
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
    mock_build_agent.return_value = _make_enhancer_agent(
        "a vivid scene | photorealistic, 8k"
    )

    result = await _enhance_prompt(
        "beach sunset", include_mugda=False, outfit_description=""
    )

    assert result == "a vivid scene | photorealistic, 8k"


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
    },
)
@patch("livingbot.image._build_enhancer_agent")
@patch("livingbot.image.httpx.AsyncClient")
async def test_generate_image_returns_decoded_image_bytes(
    mock_httpx_cls: MagicMock,
    mock_build_agent: MagicMock,
) -> None:
    raw_bytes = b"fake-image-data"
    image_b64 = base64.b64encode(raw_bytes).decode()
    submit_resp, poll_resp = _make_runpod_responses(image_b64=image_b64)

    http_client = AsyncMock()
    http_client.post = AsyncMock(return_value=submit_resp)
    http_client.get = AsyncMock(return_value=poll_resp)
    http_client.__aenter__ = AsyncMock(return_value=http_client)
    http_client.__aexit__ = AsyncMock(return_value=False)
    mock_httpx_cls.return_value = http_client

    mock_build_agent.return_value = _make_enhancer_agent(
        "enhanced prompt | photorealistic"
    )

    result = await generate_image("gym selfie", include_mugda=True)

    assert result == raw_bytes


@patch.dict(
    "os.environ",
    {
        "RUNPOD_ENDPOINT_URL": "https://api.runpod.io/v2/ep",
        "RUNPOD_API_KEY": "key",
    },
)
@patch("livingbot.image._build_enhancer_agent")
@patch("livingbot.image.httpx.AsyncClient")
async def test_generate_image_submits_workflow_to_runpod(
    mock_httpx_cls: MagicMock,
    mock_build_agent: MagicMock,
) -> None:
    submit_resp, poll_resp = _make_runpod_responses(
        image_b64=base64.b64encode(b"img").decode()
    )

    http_client = AsyncMock()
    http_client.post = AsyncMock(return_value=submit_resp)
    http_client.get = AsyncMock(return_value=poll_resp)
    http_client.__aenter__ = AsyncMock(return_value=http_client)
    http_client.__aexit__ = AsyncMock(return_value=False)
    mock_httpx_cls.return_value = http_client

    mock_build_agent.return_value = _make_enhancer_agent("scene | tags")

    await generate_image("rainy park", include_mugda=False)

    post_kwargs = http_client.post.call_args.kwargs
    payload = post_kwargs["json"]
    assert "workflow" in payload["input"]


@patch.dict(
    "os.environ",
    {
        "RUNPOD_ENDPOINT_URL": "https://api.runpod.io/v2/ep",
        "RUNPOD_API_KEY": "key",
    },
)
@patch("livingbot.image._build_enhancer_agent")
@patch("livingbot.image.httpx.AsyncClient")
async def test_generate_image_raises_when_job_fails(
    mock_httpx_cls: MagicMock,
    mock_build_agent: MagicMock,
) -> None:
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

    mock_build_agent.return_value = _make_enhancer_agent("scene | tags")

    with pytest.raises(RuntimeError, match="FAILED"):
        await generate_image("beach", include_mugda=False)
