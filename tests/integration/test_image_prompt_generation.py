"""
Integration tests that send real requests to the LLM and verify _enhance_prompt
turns a short scene idea into a good image-generation prompt for Mugda's photos.
The output is graded by a second model acting as a judge.

Run on demand: uv run pytest tests/integration/test_image_prompt_generation.py
Requires OPENROUTER_API_KEY in the environment.
"""

import os

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent

from livingbot import llm_config
from livingbot.image import _enhance_prompt

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set",
)

_JUDGE_MODEL = "openai/gpt-5.4-mini"


class _PromptVerdict(BaseModel):
    reasoning: str
    matches: bool


async def _judge(scene: str, rubric: str) -> _PromptVerdict:
    agent: Agent[None, _PromptVerdict] = Agent(
        llm_config.build_chat_model(_JUDGE_MODEL), output_type=_PromptVerdict
    )
    result = await agent.run(
        "You are evaluating a scene description written as a prompt for a Studio "
        "Ghibli style anime image generation model.\n\n"
        f"Criterion:\n{rubric}\n\n"
        f"Scene description to evaluate:\n{scene}\n\n"
        "Set matches=true if the text clearly satisfies the criterion, false if it "
        "clearly violates it."
    )
    return result.output


async def test_enhanced_scene_is_natural_language_not_tag_list() -> None:
    """The scene must read as flowing prose, not SD-style comma tag soup."""
    scene = await _enhance_prompt(
        "at the gym", include_mugda=True, outfit_description=""
    )

    verdict = await _judge(
        scene,
        rubric=(
            "The text is written as flowing natural-language sentences describing a "
            "scene. It is NOT a comma-separated list of keywords or quality tags "
            "(like 'photorealistic, 8k, cinematic lighting, sharp focus')."
        ),
    )
    assert verdict.matches, (
        f"Expected natural language, not a tag list.\n"
        f"Scene: {scene!r}\nReasoning: {verdict.reasoning}"
    )


async def test_enhanced_scene_with_mugda_describes_a_person_present() -> None:
    """When include_mugda=True, a person doing the described action must appear."""
    scene = await _enhance_prompt(
        "relaxing on the couch watching TV", include_mugda=True, outfit_description=""
    )

    verdict = await _judge(
        scene,
        rubric=(
            "The scene clearly describes a woman present and doing something "
            "resembling relaxing on a couch or watching TV."
        ),
    )
    assert verdict.matches, (
        f"Expected a person to be described in the scene.\n"
        f"Scene: {scene!r}\nReasoning: {verdict.reasoning}"
    )


async def test_enhanced_scene_without_mugda_has_no_person() -> None:
    """When include_mugda=False, the scene should be pure environment, no person."""
    scene = await _enhance_prompt(
        "a park in the evening", include_mugda=False, outfit_description=""
    )

    verdict = await _judge(
        scene,
        rubric=(
            "The scene describes only a place or environment, with no person or "
            "character present or mentioned."
        ),
    )
    assert verdict.matches, (
        f"Expected no person in a scenery-only scene.\n"
        f"Scene: {scene!r}\nReasoning: {verdict.reasoning}"
    )


async def test_enhanced_scene_with_outfit_reflects_requested_outfit() -> None:
    """The requested outfit_description should show up in the described clothing."""
    scene = await _enhance_prompt(
        "at the gym mid-workout",
        include_mugda=True,
        outfit_description="black sports bra, grey leggings, white sneakers",
    )

    verdict = await _judge(
        scene,
        rubric=(
            "The scene describes the woman wearing clothing consistent with a black "
            "sports bra, grey leggings, and white sneakers."
        ),
    )
    assert verdict.matches, (
        f"Expected the requested outfit to be reflected.\n"
        f"Scene: {scene!r}\nReasoning: {verdict.reasoning}"
    )


async def test_enhanced_scene_reflects_requested_setting() -> None:
    """The described setting should clearly match the requested location/activity."""
    scene = await _enhance_prompt(
        "at a rainy street market at night",
        include_mugda=False,
        outfit_description="",
    )

    verdict = await _judge(
        scene,
        rubric="The scene is clearly set at a street market at night in the rain.",
    )
    assert verdict.matches, (
        f"Expected the scene to reflect the requested setting.\n"
        f"Scene: {scene!r}\nReasoning: {verdict.reasoning}"
    )


async def test_enhanced_scene_does_not_restate_physical_description() -> None:
    """Face/body build is supplied separately, so the enhancer shouldn't repeat it."""
    scene = await _enhance_prompt(
        "posing for a photo at the beach", include_mugda=True, outfit_description=""
    )

    verdict = await _judge(
        scene,
        rubric=(
            "The text does NOT describe her facial features, eye color, hair color, "
            "or physical/muscular body build in detail. It may mention her briefly, "
            "but the focus is on the setting, action, and mood, not a physical "
            "description of her appearance."
        ),
    )
    assert verdict.matches, (
        f"Expected no detailed physical description.\n"
        f"Scene: {scene!r}\nReasoning: {verdict.reasoning}"
    )
