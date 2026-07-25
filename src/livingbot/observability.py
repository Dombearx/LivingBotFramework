import logging

import logfire
from logfire.exceptions import LogfireConfigError

logger = logging.getLogger(__name__)


def configure_logfire(service_name: str = "livingbot") -> None:
    try:
        logfire.configure(service_name=service_name)
    except LogfireConfigError:
        # No LOGFIRE_TOKEN and no local `logfire auth` session — fall back to
        # plain stdlib logging instead of crashing on startup.
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("livingbot").setLevel(logging.DEBUG)
        logger.warning("Logfire is not configured; continuing without it.")
        return

    logfire.instrument_pydantic_ai()
    # capture_headers stays off so RunPod/OpenRouter bearer tokens never reach Logfire.
    logfire.instrument_httpx(capture_headers=False)
    logging.basicConfig(level=logging.INFO, handlers=[logfire.LogfireLoggingHandler()])
    logging.getLogger("livingbot").setLevel(logging.DEBUG)
