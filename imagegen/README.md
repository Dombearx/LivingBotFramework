# imagegen

An HTTP service that turns a prompt into an image by running a RunPod job and
returning the result. It knows nothing about any particular persona or visual
style — callers send the finished prompt and get back an image.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/generate` | Text-to-image (RunPod `qwen-image-t2i`, or `qwen-image-t2i-lora` when LoRAs are supplied). |
| `POST` | `/generate-with-reference` | Image guided by reference images, which keeps a subject's identity consistent (RunPod `nano-banana-edit`). |
| `GET` | `/health` | Reports that the service is reachable. |

**[`API.md`](API.md) is the integration contract** — request and response
schemas, error semantics, the timeout budget, worked client examples in several
languages, and an integration checklist. Read that before writing a client.

The service also publishes its own OpenAPI spec, generated from the code so it
cannot drift: `/openapi.json` for the raw spec, `/docs` for Swagger UI, `/redoc`
for a read-only reference.

## Configuration

| Variable | Required | Purpose |
| --- | --- | --- |
| `RUNPOD_API_KEY` | yes | API key for RunPod's public endpoints. |
| `IMAGE_SERVICE_PORT` | no | Port to listen on (default `8000`). |
| `LOGFIRE_TOKEN` | no | Logfire write token for observability. |

## Running

```bash
uv sync
uv run imagegen
```

It is also built and run as its own container by the repository root's
`docker-compose.yml`, which publishes it on `http://localhost:8100`.
