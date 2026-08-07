from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from imagegen.runpod import run_job


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

    output = await run_job(client, "https://example.com", "key", {"prompt": "x"})

    assert output == {"result": "url"}
    client.get.assert_not_called()


@patch("imagegen.runpod.asyncio.sleep", new_callable=AsyncMock)
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

    output = await run_job(client, "https://example.com", "key", {"prompt": "x"})

    assert output == {"result": "done"}


async def test_run_job_raises_when_job_fails() -> None:
    client = AsyncMock()
    client.post = AsyncMock(
        return_value=_mock_response({"id": "job-3", "status": "FAILED"})
    )

    with pytest.raises(RuntimeError, match="FAILED"):
        await run_job(client, "https://example.com", "key", {"prompt": "x"})
