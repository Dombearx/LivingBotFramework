"""Generate Studio Ghibli style images of Mugda in different scenes.

Uses RunPod's qwen-image-edit-2511 public endpoint: it takes reference images
plus a prompt and edits/reframes the scene while preserving the character's
identity, so no LoRA training is needed. The "size" option lets it outpaint
into a wider landscape canvas instead of just cropping the portrait reference.

Edit the settings at the top of main() and run:
    uv run scripts/generate_mugda_ghibli.py
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from mugda_ghibli_scenes import SCENES, load_reference_images

from runpod_image_client import download_image, run_job

logger = logging.getLogger(__name__)

BASE_URL = "https://api.runpod.ai/v2/qwen-image-edit-2511"

# Largest landscape size this endpoint offers; there's no true 1920x1080 option.
SIZE = "1536*1080"


def main() -> None:
    OUTPUT_DIR = Path("images/generated")
    SEED = -1

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_dotenv()

    api_key = os.environ["RUNPOD_API_KEY"]
    reference_images = load_reference_images()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for scene_name, prompt in SCENES.items():
        payload: dict[str, object] = {
            "prompt": prompt,
            "images": reference_images,
            "size": SIZE,
            "seed": SEED,
        }

        logger.info("Submitting %s scene to %s", scene_name, BASE_URL)
        output = run_job(BASE_URL, api_key, payload)
        logger.info("%s scene completed, cost=$%s", scene_name, output.get("cost"))

        output_path = OUTPUT_DIR / f"mugda_ghibli_{scene_name}.png"
        download_image(output["result"], output_path)
        logger.info("Saved %s", output_path)


if __name__ == "__main__":
    main()
