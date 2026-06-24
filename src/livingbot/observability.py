import logging

import logfire


def configure_logfire(service_name: str = "livingbot") -> None:
    logfire.configure(service_name=service_name)
    logfire.instrument_pydantic_ai()
    # capture_headers stays off so RunPod/OpenRouter bearer tokens never reach Logfire.
    logfire.instrument_httpx(capture_headers=False)
    logging.basicConfig(level=logging.INFO, handlers=[logfire.LogfireLoggingHandler()])
    logging.getLogger("livingbot").setLevel(logging.DEBUG)
