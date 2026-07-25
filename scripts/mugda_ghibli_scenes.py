"""Shared reference images and scene prompts for the Mugda Ghibli-style scripts.

Used by generate_mugda_ghibli.py (qwen-image-edit-2511) and
generate_mugda_ghibli_nanobanana.py (nano-banana-edit) so both endpoints are
compared on identical prompts and reference images.
"""

from __future__ import annotations

import base64
from pathlib import Path

REFERENCE_IMAGE_PATHS = [
    Path("images/reference/mugda_kowal.jpeg"),
    Path("images/reference/mugda_łąka.jpeg"),
    Path("images/reference/mugda_kwiaty.jpeg"),
]

STYLE_PREFIX = (
    "Studio Ghibli style hand-painted anime illustration, warm painterly lighting. "
)

BODY_DESCRIPTION = (
    "Use the reference images only for her facial identity and body build: same "
    "face, same identity, same athletic muscular build with strong, defined arms "
    "and shoulders. Ignore the clothing, props, and background of the reference "
    "images -- dress, pose, and place her only according to the scene described "
    "below. Keep her build consistent with the references, without exaggerating "
    "it further. "
)

SCENES: dict[str, str] = {
    "gym": (
        STYLE_PREFIX
        + BODY_DESCRIPTION
        + "Same person now in the middle of a training set at the gym, mid-rep "
        "doing a barbell squat with visible strain and effort, determined focused "
        "expression, gritted teeth, sweat on her brow, wearing athletic workout "
        "clothes, dynamic action pose, full gym visible around her with weights "
        "and equipment, wide shot showing the whole scene."
    ),
    "office": (
        STYLE_PREFIX
        + BODY_DESCRIPTION
        + "Same person now sitting at a desk doing computer work in a modern "
        "office, engaged and concentrated expression with a slight thoughtful "
        "smile, wearing smart business-casual attire, wide shot showing the "
        "desk, monitor, and office space around her."
    ),
    "party": (
        STYLE_PREFIX
        + BODY_DESCRIPTION
        + "Same person now at a high-quality upscale evening party, warm joyful "
        "smile, laughing and mingling expression, wearing an elegant long dress "
        "that shows her muscular shoulders and arms, gourmet food and drinks on "
        "the table, string lights, wide shot showing the lively crowd and venue "
        "around her."
    ),
}

_MIME_TYPES = {".png": "image/png", ".jpeg": "image/jpeg", ".jpg": "image/jpeg"}


def load_reference_images() -> list[str]:
    images = []
    for path in REFERENCE_IMAGE_PATHS:
        mime_type = _MIME_TYPES[path.suffix.lower()]
        encoded = base64.b64encode(path.read_bytes()).decode()
        images.append(f"data:{mime_type};base64,{encoded}")
    return images
