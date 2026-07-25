"""Smoke test for RunPod's public qwen-image-t2i-lora endpoint.

https://console.runpod.io/hub/playground/image/qwen-image-t2i-lora

Edit the settings at the top of main() and run:
    uv run scripts/test_qwen_image_t2i_lora.py
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from runpod_image_client import download_image, run_job

logger = logging.getLogger(__name__)

# Public endpoints are addressed directly by model slug, no endpoint ID needed.
BASE_URL = "https://api.runpod.ai/v2/qwen-image-t2i-lora"


def main() -> None:
    PROMPT = (
        "Studio Ghibli style hand-painted illustration, a ferengi from Star Trek "
        "standing in the center of the frame, large lobed ears, sharp teeth, "
        "wrinkled orange-brown skin, wearing ornate jeweled business attire, "
        "whimsical lush background with soft painterly lighting, warm nostalgic "
        "color palette, anime movie art style, highly detailed"
    )
    SIZE = "1024*1024"
    SEED = -1
    # Star Trek Ferengi Race LoRA (Qwen version), trigger word: "ferengi"
    # https://civitai.com/models/851966/star-trek-ferengi-race-qwen-and-flux-and-ltx2?modelVersionId=2181392
    LORA_PATH = "https://civitai.com/api/download/models/2181392?fileId=2074510"
    LORA_SCALE = 1.0
    ENABLE_SAFETY_CHECKER = True
    OUTPUT_PATH = Path(f"qwen_t2i_lora_{datetime.now():%Y%m%d_%H%M%S}.png")

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_dotenv()

    api_key = os.environ["RUNPOD_API_KEY"]

    payload: dict[str, object] = {
        "prompt": PROMPT,
        "size": SIZE,
        "seed": SEED,
        "enable_safety_checker": ENABLE_SAFETY_CHECKER,
    }
    if LORA_PATH:
        payload["loras"] = [{"path": LORA_PATH, "scale": LORA_SCALE}]

    logger.info("Submitting job to %s", BASE_URL)
    output = run_job(BASE_URL, api_key, payload)
    logger.info("Job completed, cost=$%s", output.get("cost"))

    download_image(output["result"], OUTPUT_PATH)
    logger.info("Saved image to %s", OUTPUT_PATH)


if __name__ == "__main__":
    main()
