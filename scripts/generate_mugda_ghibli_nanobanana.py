"""Generate Studio Ghibli style images of Mugda using RunPod's nano-banana-edit.

Same reference images and prompts as generate_mugda_ghibli.py (qwen-image-edit-2511),
so the two endpoints can be compared directly. Note: nano-banana-edit has no "size"
input, so output resolution isn't controllable here.

Edit the settings at the top of main() and run:
    uv run scripts/generate_mugda_ghibli_nanobanana.py
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from mugda_ghibli_scenes import SCENES, load_reference_images

from runpod_image_client import download_image, run_job

logger = logging.getLogger(__name__)

BASE_URL = "https://api.runpod.ai/v2/nano-banana-edit"


def main() -> None:
    OUTPUT_DIR = Path("images/generated")
    ENABLE_SAFETY_CHECKER = True

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_dotenv()

    api_key = os.environ["RUNPOD_API_KEY"]
    reference_images = load_reference_images()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for scene_name, prompt in SCENES.items():
        payload: dict[str, object] = {
            "prompt": prompt,
            "images": reference_images,
            "enable_safety_checker": ENABLE_SAFETY_CHECKER,
        }

        logger.info("Submitting %s scene to %s", scene_name, BASE_URL)
        output = run_job(BASE_URL, api_key, payload)
        logger.info("%s scene completed, cost=$%s", scene_name, output.get("cost"))

        output_path = OUTPUT_DIR / f"mugda_ghibli_{scene_name}_nanobanana.png"
        download_image(output["result"], output_path)
        logger.info("Saved %s", output_path)


if __name__ == "__main__":
    main()
