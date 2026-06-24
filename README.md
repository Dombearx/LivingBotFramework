# LivingBotFramework

A Discord bot that behaves like a real person. The persona — *Mugda*, a young
woman living in Poland — chats on Discord with her own moods, plans, hobbies,
belongings, budget and stories, all of which evolve over time and shape how she
responds.

## What she does

- **Replies like a person.** She only answers when mentioned or replied to, and
  whether (and how quickly) she replies depends on her current mood and how
  worn-out she is from recent chatting.
- **Has a mood** that drifts toward neutral over time and is nudged by sleep, the
  gym and how interactions with people go.
- **Keeps a calendar.** A weekly plan is generated for her, and she records plans
  she makes mid-conversation so she knows where she is and what she's doing.
- **Remembers people.** Per-user relationships (attitude, inside jokes, interests)
  and a semantic memory of past conversations.
- **Owns things and spends within a budget.** A searchable inventory plus a weekly
  spending allowance she has to live within.
- **Grows hobbies** that level up as she spends time on them, and **tells stories**
  from her life when they fit the conversation.
- **Sends photos** of herself or her surroundings, generated on demand.

## Requirements

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) for dependency and task management

## Configuration

The bot is configured entirely through environment variables:

| Variable | Required | Purpose |
| --- | --- | --- |
| `DISCORD_BOT_TOKEN` | yes | Discord bot token used to connect. |
| `OPENROUTER_API_KEY` | yes | API key for the chat and helper models (via OpenRouter). |
| `OPENROUTER_BASE_URL` | no | Override the OpenRouter base URL. |
| `RUNPOD_ENDPOINT_URL` | for photos | RunPod endpoint that runs the image workflow. |
| `RUNPOD_API_KEY` | for photos | RunPod API key. |

Persistent state (memories, calendar, mood, inventory, spending, hobbies,
stories and story images) is written under `data/`.

## Running

Install dependencies and start the bot:

```bash
uv sync
uv run livingbot
```

To run the bot together with the local admin dashboard (NiceGUI, served on
`http://127.0.0.1:8080`):

```bash
uv run livingbot-admin
```

## Development

After any change, run, in order:

```bash
uv run ruff format . && uv run ruff check .
uv run pytest
```

Both must pass before committing. Integration tests live under
`tests/integration/` and are excluded from the default `pytest` run.
