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
| `RUNPOD_API_KEY` | for photos | RunPod API key (calls RunPod's public nano-banana-edit and qwen-image-t2i endpoints). |

The memory subsystem (mem0) is configured to route its LLM calls and
embeddings through OpenRouter using `OPENROUTER_API_KEY` above — no separate
OpenAI key is needed.

Persistent state (memories, calendar, mood, inventory, spending, hobbies,
stories and story images) is written under `data/`.

## Running

Install dependencies and start the bot:

```bash
uv sync
uv run livingbot
```

To run the bot together with the local admin dashboard (NiceGUI, served on
`http://0.0.0.0:9080`):

```bash
uv run livingbot-admin
```

## Deployment

`docker compose up -d` (or `make up`) builds and runs the bot together with
the admin dashboard, matching `uv run livingbot-admin` above. `data/` is
mounted as a volume so persistent state survives rebuilds. See the `Makefile`
for `up`/`down`/`build`/`restart`/`logs` targets.

`make up` also starts `livingbot-update-server` directly on the host,
alongside the `docker compose` stack (`make down` stops both). It exposes a
`GET /update` endpoint, on port 40000 by default, that runs `git pull`
followed by `docker compose up -d --build --force-recreate` in this
directory, redeploying the bot with whatever is on `main`. It runs on the
host rather than in a container so it can invoke `git` and `docker` directly
without socket or bind-mount tricks. The endpoint has no authentication of
its own; it's meant to be reachable only over a private network (e.g.
Netbird), such as from the `deploy.yml` GitHub Actions workflow, which calls
it after every merge to `main`.

## Development

After any change, run, in order:

```bash
uv run ruff format . && uv run ruff check .
uv run pytest
```

Both must pass before committing. Integration tests live under
`tests/integration/` and are excluded from the default `pytest` run.
