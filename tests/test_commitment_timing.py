from unittest.mock import AsyncMock, MagicMock, patch

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from livingbot.commitment_timing import CommitmentTimingDecision, CommitmentTimingJudge


@patch.object(Agent, "run", new_callable=AsyncMock)
async def test_decide_returns_the_models_decision(mock_run: AsyncMock) -> None:
    decision = CommitmentTimingDecision(should_follow_up=True, reason="she's home now")
    mock_run.return_value = MagicMock(output=decision)
    judge = CommitmentTimingJudge(TestModel())

    result = await judge.decide("some context")

    assert result == decision


@patch.object(Agent, "run", new_callable=AsyncMock, side_effect=RuntimeError("boom"))
async def test_decide_returns_none_when_the_model_call_fails(
    mock_run: AsyncMock,
) -> None:
    judge = CommitmentTimingJudge(TestModel())

    result = await judge.decide("some context")

    assert result is None
