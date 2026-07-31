import logging
import os
import subprocess

import uvicorn
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from livingbot.observability import configure_logfire

logger = logging.getLogger(__name__)

UPDATE_SERVER_HOST = "0.0.0.0"
DEFAULT_UPDATE_SERVER_PORT = 40000

app = FastAPI()


@app.get("/restart", response_class=PlainTextResponse)
def restart() -> PlainTextResponse:
    logger.info("Received restart request")

    pull = subprocess.run(["git", "pull"], capture_output=True, text=True)
    if pull.returncode != 0:
        return PlainTextResponse(
            f"Failed to pull latest code\n{pull.stderr}", status_code=500
        )

    up = subprocess.run(
        ["docker", "compose", "up", "-d", "--build", "--force-recreate"],
        capture_output=True,
        text=True,
    )
    if up.returncode != 0:
        return PlainTextResponse(
            "Failed to restart service\n"
            f"Status: {up.returncode}\n{up.stdout}\n{up.stderr}",
            status_code=500,
        )

    return PlainTextResponse(
        f"Service restarted successfully\n{pull.stdout}\n{up.stdout}"
    )


def run() -> None:
    configure_logfire(service_name="livingbot-update-server")
    port = int(os.environ.get("UPDATE_SERVER_PORT", DEFAULT_UPDATE_SERVER_PORT))
    uvicorn.run(app, host=UPDATE_SERVER_HOST, port=port)
