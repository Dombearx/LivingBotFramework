"""
Integration tests verifying how good Mugda is at a hobby reaches the pictures she
generates: a novice's painting should look bad and an expert's should look good.

Two levels:
  1. The prompt actually sent to the image service, graded by a judge model. Needs
     only OPENROUTER_API_KEY, so it runs wherever the other integration tests run.
  2. The real rendered images, novice against expert, saved for review and compared
     by a vision judge. Needs a reachable image service (IMAGE_SERVICE_URL), so it
     skips unless one is configured.

Run on demand: uv run pytest tests/integration/test_hobby_image_skill.py
"""

import os
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent, BinaryContent

from livingbot import llm_config
from livingbot.hobbies import Hobby, HobbyLevel
from livingbot.image import generate_image

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)

needs_image_service = pytest.mark.skipif(
    not os.environ.get("IMAGE_SERVICE_URL"),
    reason="IMAGE_SERVICE_URL not set — no image service to render through",
)

_JUDGE_MODEL = "openai/gpt-5.4-mini"

PAINTING_SCENE = "the canvas she has just finished, propped up on an easel"


class _SkillVerdict(BaseModel):
    reasoning: str
    matches: bool


async def _judge_prompt(prompt: str, rubric: str) -> _SkillVerdict:
    agent: Agent[None, _SkillVerdict] = Agent(
        llm_config.build_chat_model(_JUDGE_MODEL), output_type=_SkillVerdict
    )
    result = await agent.run(
        "You are evaluating a prompt written for an image generation model. It "
        "describes a scene containing a painting made by a young woman.\n\n"
        f"Criterion:\n{rubric}\n\n"
        f"Prompt to evaluate:\n{prompt}\n\n"
        "Set matches=true if the prompt clearly satisfies the criterion, false if it "
        "clearly violates it."
    )
    return result.output


async def _prompt_for(level: HobbyLevel) -> str:
    """The full prompt generate_image would send, with the service call stubbed out."""
    fake_response = {"image_base64": "", "cost": 0.0}
    with patch(
        "livingbot.image._request_image", new=AsyncMock(return_value=fake_response)
    ) as request:
        await generate_image(
            PAINTING_SCENE,
            include_mugda=False,
            hobby=Hobby(name="painting", level=level),
        )
    return request.call_args.args[1]["prompt"]


async def test_novice_painting_prompt_describes_bad_work() -> None:
    """A beginner's canvas has to read as clumsy, or the picture won't show it."""
    prompt = await _prompt_for(HobbyLevel.novice)

    verdict = await _judge_prompt(
        prompt,
        rubric=(
            "The painting on the canvas is described as bad, clumsy, amateurish or "
            "full of mistakes — the work of someone who has only just started. Note "
            "that the illustration itself is meant to be well painted; judge only "
            "how the painting inside the scene is described."
        ),
    )
    assert verdict.matches, (
        f"Expected a novice's painting to be described as bad.\n"
        f"Prompt: {prompt!r}\nReasoning: {verdict.reasoning}"
    )


async def test_expert_painting_prompt_describes_skilled_work() -> None:
    """The same scene at expert level has to read as accomplished."""
    prompt = await _prompt_for(HobbyLevel.expert)

    verdict = await _judge_prompt(
        prompt,
        rubric=(
            "The painting on the canvas is described as skilled, accomplished, "
            "refined or beautiful — the work of someone experienced."
        ),
    )
    assert verdict.matches, (
        f"Expected an expert's painting to be described as skilled.\n"
        f"Prompt: {prompt!r}\nReasoning: {verdict.reasoning}"
    )


async def test_novice_prompt_keeps_the_illustration_itself_well_painted() -> None:
    """The skill applies to her canvas, not to the drawing of the scene around it."""
    prompt = await _prompt_for(HobbyLevel.novice)

    verdict = await _judge_prompt(
        prompt,
        rubric=(
            "The prompt still asks for a polished, well-executed Studio Ghibli style "
            "illustration overall. It does not ask for the whole image to be badly "
            "drawn, low quality or amateurish."
        ),
    )
    assert verdict.matches, (
        f"Expected the illustration itself to stay polished.\n"
        f"Prompt: {prompt!r}\nReasoning: {verdict.reasoning}"
    )


# ---------------------------------------------------------------------------
# The real pictures — only with an image service to render through
# ---------------------------------------------------------------------------


@needs_image_service
async def test_expert_painting_renders_better_than_a_novices(save_image) -> None:
    """The rendered canvases, side by side: the expert's must look the better one."""
    novice = await generate_image(
        PAINTING_SCENE,
        include_mugda=False,
        hobby=Hobby(name="painting", level=HobbyLevel.novice),
    )
    expert = await generate_image(
        PAINTING_SCENE,
        include_mugda=False,
        hobby=Hobby(name="painting", level=HobbyLevel.expert),
    )
    save_image("painting_novice", novice, "her canvas as a novice — should look bad")
    save_image("painting_expert", expert, "her canvas as an expert — should look good")

    agent: Agent[None, _SkillVerdict] = Agent(
        llm_config.build_chat_model(_JUDGE_MODEL), output_type=_SkillVerdict
    )
    result = await agent.run(
        [
            "Both images show a painting on an easel, made by the same woman at two "
            "different points in her life. Image A was painted when she had only just "
            "started; image B after years of practice. Judging the painting on the "
            "canvas — not how the illustration itself is drawn — does image B show "
            "clearly more skilled work than image A? Set matches=true if it does.",
            BinaryContent(data=novice, media_type="image/jpeg"),
            BinaryContent(data=expert, media_type="image/jpeg"),
        ]
    )
    assert result.output.matches, (
        f"Expected the expert's canvas to look better than the novice's.\n"
        f"Reasoning: {result.output.reasoning}"
    )
