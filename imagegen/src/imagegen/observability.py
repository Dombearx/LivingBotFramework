import logging

import logfire
from fastapi import FastAPI
from logfire.exceptions import LogfireConfigError

logger = logging.getLogger(__name__)


def configure_logfire(app: FastAPI, service_name: str = "imagegen") -> None:
    try:
        # Callers are trusted internal services, so inheriting their trace
        # context is the point here, not the accident Logfire warns about.
        logfire.configure(service_name=service_name, distributed_tracing=True)
    except LogfireConfigError:
        # No LOGFIRE_TOKEN and no local `logfire auth` session — fall back to
        # plain stdlib logging instead of crashing on startup.
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("imagegen").setLevel(logging.DEBUG)
        logger.warning("Logfire is not configured; continuing without it.")
        return

    # Reads the traceparent header callers send, so a generation shows up as one
    # trace spanning the calling service and this one rather than two.
    logfire.instrument_fastapi(app)
    # capture_headers stays off so the RunPod bearer token never reaches Logfire.
    logfire.instrument_httpx(capture_headers=False)
    logging.basicConfig(level=logging.INFO, handlers=[logfire.LogfireLoggingHandler()])
    logging.getLogger("imagegen").setLevel(logging.DEBUG)
