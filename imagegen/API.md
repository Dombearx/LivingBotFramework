# Image generation service — API reference

Turns a prompt into an image by running a RunPod job and returning the result.

This document is the integration contract. It is written to be enough on its
own: everything needed to build a working client is here, including the failure
modes and the operational limits that are easy to get wrong.

## Quick reference

| Method | Path | Purpose | Slow? |
| --- | --- | --- | --- |
| `GET` | `/health` | Liveness check | no |
| `POST` | `/generate` | Text-to-image, optionally with LoRA adapters | yes |
| `POST` | `/generate-with-reference` | Image guided by reference images of a subject | yes |

Both generation endpoints take JSON and return the same
[`GenerateResponse`](#generateresponse).

## Machine-readable spec

The service publishes its own OpenAPI 3.1 spec, generated from the code, so it
cannot drift from the implementation:

| URL | What |
| --- | --- |
| `/openapi.json` | The spec. Self-contained — feed it to a client generator, Postman, or an agent. |
| `/docs` | Swagger UI, with "Try it out" to send real requests. |
| `/redoc` | ReDoc, a read-only reference. |

`/docs` and `/redoc` load their assets from `cdn.jsdelivr.net` in the viewer's
browser, so they render blank on a machine with no internet access.
`/openapi.json` has no external dependencies and always works.

To get the spec without running the service:

```bash
cd imagegen && uv run python -c \
  "import json; from imagegen.app import app; print(json.dumps(app.openapi(), indent=2))"
```

## Base URL

The service listens on port `8000` inside its container, published on `8100` of
the Docker host. Within the repository's `docker-compose.yml` network it is
reachable as `http://image-service:8000`.

There is no path prefix and no versioning in the URL. Pick the base URL up from
configuration rather than hardcoding it.

## Authentication

None. The service is expected to run on a private network, and it will answer
any request that reaches it. Two consequences for integrators:

- Do not put it anywhere untrusted. Every call spends real money.
- Do not send credentials to it. It has no use for them and does not read
  `Authorization`.

## Conventions

- Requests and responses are `application/json`, UTF-8.
- Images come back **base64-encoded without a data URI prefix**. Decode to get
  raw bytes.
- Reference images go **in** as data URIs, *with* the prefix. The asymmetry is
  deliberate: RunPod's edit model wants data URIs, and callers usually want raw
  bytes back.
- Unknown fields in a request body are **ignored, not rejected**. A typo in an
  optional field name fails silently, so check names against this document.

---

## `GET /health`

Reports that the process is serving.

```bash
curl http://image-service:8000/health
# ok
```

Returns `200` with the plain-text body `ok`. It does **not** call RunPod, so a
healthy response does not mean generation works — it will return `ok` even when
`RUNPOD_API_KEY` is missing and every generation call would fail. Treat it as a
liveness/readiness probe only.

---

## `POST /generate`

Renders a prompt with no subject to keep consistent. Backed by RunPod's
`qwen-image-t2i`, or `qwen-image-t2i-lora` when adapters are supplied.

Use it for scenery, objects, and any scene where nothing has to look the same as
it did in a previous image.

### Request

| Field | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `prompt` | string | yes | — | Non-empty. The complete prompt; see [Prompting](#prompting). |
| `seed` | integer | no | `-1` | `-1` means random. Fixed non-negative values make results reproducible. |
| `loras` | array of [`Lora`](#lora) | no | `[]` | Supplying any reroutes to the LoRA endpoint. |

```json
{
  "prompt": "Studio Ghibli style hand-painted anime illustration, a quiet park path at dusk, warm painterly lighting",
  "seed": -1,
  "loras": []
}
```

### LoRA adapters

Supplying a non-empty `loras` array switches the job to a **different RunPod
endpoint** (`qwen-image-t2i-lora`), because the plain text-to-image endpoint
rejects the field. This is transparent to the caller but has consequences:

- Jobs take longer, since RunPod downloads the adapter weights per job.
- The cost differs from a plain text-to-image job.
- `path` must be reachable **from RunPod**, not from you — it is fetched
  server-side. A URL that only resolves on your private network will fail.

```json
{
  "prompt": "a quiet park path at dusk",
  "loras": [{ "path": "https://civitai.com/api/download/models/2181392", "scale": 1.0 }]
}
```

---

## `POST /generate-with-reference`

Renders a prompt while keeping a subject consistent with supplied reference
images. Backed by RunPod's `nano-banana-edit`, a hosted Gemini image model that
reads the references to preserve the subject's face, build and identity.

Use it whenever a specific person or character has to be recognisably the same
across a series of images.

### Request

| Field | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `prompt` | string | yes | — | Non-empty. Describe how the subject appears in the new scene. |
| `reference_images` | array of string | yes | — | At least one. Base64 data URIs. |

```json
{
  "prompt": "the woman from the reference photos, sitting on a park bench at dusk",
  "reference_images": ["data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAA..."]
}
```

### Reference images

Format is `data:<mime-type>;base64,<data>`. `image/jpeg` and `image/png` are
known to work.

```python
import base64
from pathlib import Path

def to_data_uri(path: Path, mime_type: str) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime_type};base64,{encoded}"
```

Practical notes:

- **The service stores nothing.** There is no upload step, no reference library
  and no subject registry. Every call carries its own references, which is why
  the service stays generic across callers.
- Supply references of **the same subject**. Multiple angles help identity hold.
- Base64 inflates bytes by roughly a third. Three 3 MB photos become a ~13 MB
  request body. That is fine over a local network and wasteful over anything
  slower — downscale before encoding.

### Not supported here

`seed` and `loras` do not apply to this endpoint. The underlying model accepts
only a prompt and images. Sending them is **silently ignored, not rejected** —
you will get an image back that took no notice of either.

---

## Shared types

### `Lora`

| Field | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `path` | string | yes | — | Non-empty. Public URL RunPod downloads weights from. |
| `scale` | number | no | `1.0` | Strength. Lower blends with the base model. |

### `GenerateResponse`

Returned by both generation endpoints on success.

| Field | Type | Nullable | Notes |
| --- | --- | --- | --- |
| `image_base64` | string | no | The image, base64, **no data URI prefix**. |
| `cost` | number | **yes** | USD RunPod charged. `null` when not reported. |

```json
{ "image_base64": "iVBORw0KGgoAAAANSUhEUg...", "cost": 0.021 }
```

Two things to handle:

- **`cost` can be `null`.** Do not assume a number when logging or summing.
- **The image format is not guaranteed.** The service returns whatever the model
  produced and does not convert. Detect the format from the decoded bytes (magic
  number) rather than assuming an extension.

```python
image_bytes = base64.b64decode(response["image_base64"])
```

---

## Errors

| Status | Meaning | Retry? |
| --- | --- | --- |
| `200` | Success. | — |
| `422` | Request body failed validation — missing `prompt`, empty string, empty `reference_images`. Body lists the offending fields. | No. Fix the request. |
| `500` | Upstream failure: RunPod job failed or timed out, image download failed, or `RUNPOD_API_KEY` is unset on the service. | Maybe, with backoff. |

**`500` carries no machine-readable failure code.** It is FastAPI's default
error payload, so a caller cannot distinguish "RunPod is briefly busy" from
"the service is misconfigured". Treat every `500` as a generic upstream failure:
retry a small number of times with backoff, then give up and surface a failure
to your user. Do not parse the body to branch on the cause.

**The service does not retry internally.** One request is one RunPod job. If you
want retries, implement them in your client — and note that a retry is a second
billable job.

---

## Timeouts and latency

Generation is **synchronous**. The request blocks until the image is ready.

Worst case, derived from the service's own limits:

| Phase | Limit |
| --- | --- |
| Submit job (`/runsync`, blocks server-side) | 100 s |
| Poll until complete | 180 s |
| Download the finished image | 60 s |
| **Total worst case** | **≈ 350 s** |

**Set a client timeout of at least 360 seconds.** A shorter timeout will abandon
jobs that would have succeeded — and you are billed for them anyway, because the
RunPod job runs to completion regardless of whether anyone is still listening.

There is **no job handle, callback, or polling API**. A dropped connection loses
the result permanently. If your caller cannot hold a connection that long, put a
queue in front of the service rather than shortening the timeout.

Typical successful calls are far faster than the worst case, but treat the
latency as unbounded-ish and never call this on a latency-sensitive path.

## Concurrency and rate limits

The service imposes none. It does not queue, throttle, or cap concurrent jobs —
every request goes straight to RunPod. Concurrency limits and spend control are
the caller's responsibility, and RunPod's.

## Cost

Every successful call costs money, reported per-job in `cost`. There is no
free path, no cache and no deduplication: two identical requests are two
billable jobs. Build your integration accordingly — cache results on your side
if you might ask for the same image twice.

## Prompting

The service applies **no styling, rewriting or prompt enhancement**. What you
send is what the model sees. Style, composition, lighting and any persona
wording must all be in `prompt`.

This is intentional. Style is the caller's identity, not the service's, which is
what lets different callers share one service without inheriting each other's
look. If you want LLM-based prompt enhancement, do it before calling.

---

## Worked examples

### curl

```bash
curl -X POST http://image-service:8000/generate \
  -H 'Content-Type: application/json' \
  --max-time 360 \
  -d '{"prompt": "a quiet park path at dusk, warm painterly lighting"}' \
  | python3 -c "import base64,json,sys; open('out.png','wb').write(base64.b64decode(json.load(sys.stdin)['image_base64']))"
```

### Python (async, httpx)

```python
import base64

import httpx

BASE_URL = "http://image-service:8000"
TIMEOUT_SECONDS = 360.0


async def generate(prompt: str) -> bytes:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/generate",
            json={"prompt": prompt},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return base64.b64decode(response.json()["image_base64"])


async def generate_with_reference(prompt: str, reference_images: list[str]) -> bytes:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/generate-with-reference",
            json={"prompt": prompt, "reference_images": reference_images},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return base64.b64decode(response.json()["image_base64"])
```

### Python (sync, requests)

```python
import base64

import requests

response = requests.post(
    "http://image-service:8000/generate",
    json={"prompt": "a quiet park path at dusk"},
    timeout=360,
)
response.raise_for_status()
image_bytes = base64.b64decode(response.json()["image_base64"])
```

### TypeScript

```ts
const BASE_URL = "http://image-service:8000";

export async function generate(prompt: string): Promise<Uint8Array> {
  const response = await fetch(`${BASE_URL}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
    signal: AbortSignal.timeout(360_000),
  });
  if (!response.ok) {
    throw new Error(`image generation failed: ${response.status}`);
  }
  const { image_base64 } = await response.json();
  return Uint8Array.from(atob(image_base64), (c) => c.charCodeAt(0));
}
```

---

## Integration checklist

- [ ] Base URL read from configuration, not hardcoded.
- [ ] Client timeout ≥ 360 s on both generation endpoints.
- [ ] `cost` handled as nullable.
- [ ] Image format detected from bytes, not assumed.
- [ ] `500` treated as a generic failure, retried with backoff at most a few
      times, then surfaced.
- [ ] `422` treated as a permanent request bug, never retried.
- [ ] Reference images downscaled before base64 encoding.
- [ ] Concurrency capped on your side; the service will not do it for you.
- [ ] Results cached if the same image might be requested twice.

## What this service does not do

Stated explicitly, because each one is a reasonable thing to assume:

- No prompt enhancement or styling.
- No stored reference images, subjects or presets.
- No authentication.
- No retries, queueing, rate limiting or spend caps.
- No async job handles — one request, one blocking call, no way to resume.
- No image format conversion, resizing or post-processing.
- No caching or deduplication.
