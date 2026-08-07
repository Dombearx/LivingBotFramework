# imagegen

An HTTP service that turns a prompt into an image by running a RunPod job and
returning the result. It knows nothing about any particular persona or visual
style — callers send the finished prompt and get back an image.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/generate` | Text-to-image (RunPod `qwen-image-t2i`, or `qwen-image-t2i-lora` when LoRAs are supplied). |
| `POST` | `/generate-with-reference` | Image edit guided by reference images, which keeps a subject's identity consistent (RunPod `nano-banana-edit`). |
| `GET` | `/health` | Reports that the service is reachable. |

`POST /generate`

```json
{
  "prompt": "a quiet park path at dusk",
  "seed": -1,
  "loras": [{ "path": "https://civitai.com/api/download/models/...", "scale": 1.0 }]
}
```

`loras` is optional and defaults to empty. Supplying it switches the job to
RunPod's `qwen-image-t2i-lora` endpoint, since the plain `qwen-image-t2i` one
rejects the field; leaving it out keeps the plain endpoint. `scale` defaults to
`1.0`. There is no equivalent on `/generate-with-reference`: `nano-banana-edit`
is a hosted Gemini model that takes only a prompt and images.

`POST /generate-with-reference`

```json
{
  "prompt": "she is sitting on a bench, ...",
  "reference_images": ["data:image/jpeg;base64,..."]
}
```

Both return

```json
{ "image_base64": "...", "cost": 0.021 }
```

`cost` is what RunPod charged for the job, and is `null` when RunPod doesn't
report one. Generation polls RunPod for up to three minutes, so clients need a
request timeout longer than that.

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
