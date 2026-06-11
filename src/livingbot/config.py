from datetime import timedelta
from pathlib import Path

MEMORY_DATA_PATH = Path("data/memories")
MOOD_DATA_PATH = Path("data/mood")
RELATION_DATA_PATH = Path("data/relations")
CALENDAR_DATA_PATH = Path("data/calendar")
INVENTORY_DATA_PATH = Path("data/inventory")
SPENDING_DATA_PATH = Path("data/spending")
HOBBY_DATA_PATH = Path("data/hobbies")
STORY_DATA_PATH = Path("data/stories")
STORY_IMAGE_PATH = Path("data/story_images")
HOME_LOCATION = "home"
DEFAULT_HOBBIES = ["gym"]
LIFE_LOOP_INTERVAL_SECONDS = 3600
PHOTO_COOLDOWN_MIN = 40
PHOTO_COOLDOWN_MAX = 60
STORY_TIED_TO_PLAN_PROBABILITY = 0.3
STORY_ACTIVE_HOUR_START = 8
STORY_ACTIVE_HOUR_END = 23
STORY_AVOID_RECENT_LIMIT = 20
ONBOARDING_PERIOD = timedelta(days=3)
ONBOARDING_RESPONSE_BOOST = 2.0
ONBOARDING_REST_DELAY_DIVISOR = 4.0
