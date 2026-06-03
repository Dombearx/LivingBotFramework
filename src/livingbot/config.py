from pathlib import Path

LLM_MODEL = "openai:gpt-4o"
SYSTEM_PROMPT = (
    "You are Mugda, a young woman living in Poland. "
    "You chat on Discord like a real person, with your own life, moods and plans. "
    "You keep a personal calendar: when you make, change or cancel plans during a "
    "conversation, record them with the add_plan and remove_plan tools so you "
    "remember where you will be."
)
MEMORY_DATA_PATH = Path("data/memories")
RELATION_DATA_PATH = Path("data/relations")
CALENDAR_DATA_PATH = Path("data/calendar")
HOME_LOCATION = "home"
HOBBIES = ["gym"]
LIFE_LOOP_INTERVAL_SECONDS = 3600

# How an ongoing event suppresses her replies. The reply weight is added to her
# tiredness when rolling whether to answer now (higher -> less likely). The rest
# minutes are added to how long she stays quiet between attempts while busy, so she
# does not keep re-rolling through a long session.
BUSYNESS_REPLY_WEIGHT: dict[str, float] = {"light": 1.0, "moderate": 3.0, "deep": 10.0}
BUSYNESS_REST_MINUTES: dict[str, float] = {"light": 5.0, "moderate": 15.0, "deep": 45.0}
