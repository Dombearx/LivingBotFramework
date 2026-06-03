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
