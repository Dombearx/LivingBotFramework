from unittest.mock import MagicMock, patch

from logfire.exceptions import LogfireConfigError

from livingbot.observability import configure_logfire


@patch("livingbot.observability.logfire")
def test_configure_logfire_falls_back_when_not_configured(
    mock_logfire: MagicMock,
) -> None:
    mock_logfire.configure.side_effect = LogfireConfigError("not logged in")

    configure_logfire()

    mock_logfire.instrument_pydantic_ai.assert_not_called()
    mock_logfire.instrument_httpx.assert_not_called()


@patch("livingbot.observability.logfire")
def test_configure_logfire_instruments_pydantic_ai_and_httpx_when_configured(
    mock_logfire: MagicMock,
) -> None:
    configure_logfire()

    mock_logfire.instrument_pydantic_ai.assert_called_once()
    mock_logfire.instrument_httpx.assert_called_once_with(capture_headers=False)


@patch("livingbot.observability.logfire")
def test_configure_logfire_passes_service_name(mock_logfire: MagicMock) -> None:
    configure_logfire(service_name="livingbot-admin")

    mock_logfire.configure.assert_called_once_with(service_name="livingbot-admin")
