import logging

import logfire


def configure_logfire() -> None:
    logfire.configure()
    logfire.instrument_pydantic_ai()
    logging.basicConfig(level=logging.INFO, handlers=[logfire.LogfireLoggingHandler()])
    logging.getLogger("livingbot").setLevel(logging.DEBUG)
