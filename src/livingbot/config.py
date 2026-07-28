from datetime import timedelta
from pathlib import Path

MEMORY_DATA_PATH = Path("data/memories")
MOOD_DATA_PATH = Path("data/mood")
RELATION_DATA_PATH = Path("data/relations")
CALENDAR_DATA_PATH = Path("data/calendar")
ACTIVITY_NOTES_DATA_PATH = Path("data/activity_notes")
INVENTORY_DATA_PATH = Path("data/inventory")
SPENDING_DATA_PATH = Path("data/spending")
HOBBY_DATA_PATH = Path("data/hobbies")
PREFERENCE_DATA_PATH = Path("data/preferences")
HOBBY_COOLDOWN = timedelta(days=14)
RECENT_HOBBY_WINDOW = timedelta(days=14)
RECENT_PURCHASE_WINDOW = timedelta(days=7)
STORY_DATA_PATH = Path("data/stories")
STORY_IMAGE_PATH = Path("data/story_images")
# Reference photos of Mugda passed to the image-editing model so generated
# selfies keep the same face and body build.
MUGDA_REFERENCE_IMAGE_PATHS = [
    Path("images/reference/mugda_kowal.jpeg"),
    Path("images/reference/mugda_łąka.jpeg"),
    Path("images/reference/mugda_kwiaty.jpeg"),
]
SPONTANEOUS_DATA_PATH = Path("data/spontaneous")
COMMITMENT_DATA_PATH = Path("data/commitments")
PHOTO_COOLDOWN_DATA_PATH = Path("data/photo_cooldown")
HOME_LOCATION = "home"
DEFAULT_HOBBIES = ["gym"]
LIFE_LOOP_INTERVAL_SECONDS = 3600
PHOTO_COOLDOWN_MIN = 40
PHOTO_COOLDOWN_MAX = 60
STORY_TIED_TO_PLAN_PROBABILITY = 0.3
# The hours she is awake and active; outside this window she is asleep.
AWAKE_HOUR_START = 8
AWAKE_HOUR_END = 23
STORY_AVOID_RECENT_LIMIT = 20
# How many prior channel messages to automatically pull in as context each
# time she responds, so replies don't come out of nowhere.
CHANNEL_HISTORY_LIMIT = 20
# Channel she drops the occasional unprompted message into. Set this to the
# hardcoded channel's ID; while it is None she never posts on her own.
RANDOM_POST_CHANNEL_ID: int | None = 1184946204333850694
RANDOM_POST_MIN_DAYS = 7.0
RANDOM_POST_MAX_DAYS = 10.0
# How long a message must have sat unanswered before she is told why she is only
# getting to it now. Below this, a reply is prompt enough to need no explanation.
DELAY_EXPLANATION_THRESHOLD = timedelta(minutes=20)
ONBOARDING_PERIOD = timedelta(days=3)
ONBOARDING_RESPONSE_BOOST = 2.0
ONBOARDING_REST_DELAY_DIVISOR = 4.0
