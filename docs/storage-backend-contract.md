# Storage Backend Contract (2026-05-11)

> This document governs the interface every concrete storage backend must
> satisfy. It is the single source of truth for **Lane P (Storage Providers
> Agent)** — anyone writing an Aliyun OSS / Tencent COS / Cloudflare R2 /
> AWS S3 / MinIO adapter must implement against the surface defined here.
>
> The Protocol, the `LocalBackend`, and the factory live in
> `backend/app/core/storage_backend.py`. The cloud adapters live in
> `backend/app/core/storage_backends/{aliyun,tencent,aws_like}.py`. Lane P
> may **only** modify those files plus the factory's dispatch branches; the
> Protocol surface itself is frozen.

## 1. Purpose

This contract decouples "where bytes physically land" from the rest of the
backend (generator / task_manager / uploads / history). Any concrete
implementation that fulfils the four-method Protocol can be plugged in via
config without touching call sites. The default is the historical
filesystem-backed `LocalBackend`; cloud providers are opt-in via the
`storage` config section.

## 2. `StorageBackend` Protocol

The verbatim signatures (see `backend/app/core/storage_backend.py`):

```python
class StorageBackend(Protocol):
    def save(self, key: str, content: bytes, *, content_type: str | None = None) -> None: ...
    def url(self, key: str) -> str: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
```

Per-method semantics:

- **`save(key, content, *, content_type=None)`** — write `content` to the
  storage location identified by `key`. Adapters prepend their own `prefix`
  before talking to the SDK. `content_type` is a best-effort hint forwarded
  to the SDK (e.g. `Content-Type` header) when the backend supports it;
  `LocalBackend` ignores it. Overwriting an existing key is allowed and the
  contract makes no guarantee of atomicity beyond what the SDK provides.

- **`url(key) -> str`** — return a client-facing URL for `key`. Strategy is
  detailed in §4. `url()` MAY be called on a key that does not exist yet —
  adapters MUST NOT make a HEAD probe before returning. For presigned URLs
  the eventual GET will surface the 404; for public URLs the client sees the
  404 from the CDN. Either way, `url()` itself does not raise on missing
  keys.

- **`delete(key)`** — remove the object at `key`. **No-raise on missing**:
  if the underlying SDK returns a `NoSuchKey` / 404, the adapter MUST
  swallow it. Other failures (auth, network) are wrapped in
  `StorageError`. Callers (e.g. `api/history.py`) typically catch
  `StorageError` and log without aborting the DB delete.

- **`exists(key) -> bool`** — return `True` iff the object exists. A 404
  response from the SDK is mapped to `False`. Any other SDK failure is
  wrapped in `StorageError`.

## 3. Key naming

The application layer always passes a **clean key** without any prefix:

- Generated outputs: `generated_{task_id}.{ext}` (e.g.
  `generated_4c2b1e8a-....jpeg`).
- img2img reference uploads: `temp/{sha1}.{ext}` (e.g.
  `temp/0fc1abcd....png`).

Adapters are responsible for prepending their configured `prefix` internally
inside every method (`save` / `url` / `delete` / `exists`). The application
layer NEVER prefixes the key itself. `prefix` may be empty (the default).

## 4. URL strategy

`url(key)` produces one of three shapes depending on configuration:

1. **Local backend** — returns `/images/{key}`. The FastAPI app mounts
   `images_dir` at `/images/` via `StaticFiles`, so the browser fetches the
   bytes directly from disk.
2. **Cloud backend with `public_base_url` set** — returns
   `{public_base_url.rstrip('/')}/{prefix}{key}`. This is the path users
   pick when they have a CDN / custom domain in front of the bucket. No
   signing happens; the URL is plain and shareable.
3. **Cloud backend with `public_base_url` empty** — returns a **presigned
   GET URL** with `ExpiresIn=3600` (1 hour). The adapter must use whatever
   the SDK exposes (boto3 `generate_presigned_url`, oss2 `bucket.sign_url`,
   `qcloud_cos.get_presigned_url`, etc.).

Adapters MUST NOT log presigned URLs — the signature in the query string is
a bearer credential for the TTL.

## 5. `StorageError`

```python
class StorageError(RuntimeError):
    def __init__(self, provider: str, op: str, key: str | None, cause: Exception | None = None): ...
```

Every SDK exception adapters surface MUST be wrapped in `StorageError` with:

- `provider` — short backend name (`"aliyun"`, `"tencent"`, `"cloudflare"`,
  `"aws"`, `"minio"`).
- `op` — one of `"save"`, `"url"`, `"delete"`, `"exists"`.
- `key` — the key being acted on, or `None` for URL-style errors where no
  specific key applies.
- `cause` — the original SDK exception.

The orchestrator (e.g. `api/history.py`, `api/tasks.py`) decides whether to
map a `StorageError` to HTTP 500 or simply log and continue (history delete
falls back to a logged warning so the DB row still gets removed).

## 6. Factory

```python
def build_storage_backend(cfg: StorageConfig, *, images_dir: Path) -> StorageBackend: ...
```

For Lane P: replace each `NotImplementedError` branch with something like:

```python
if cfg.backend == "aliyun":
    from .storage_backends.aliyun import AliyunOSSBackend  # lazy import
    return AliyunOSSBackend(cfg.aliyun)
```

Notes:

- Import the adapter **lazily inside the branch** so a missing SDK only
  breaks the deployments that actually opted into that provider.
- Pass the provider-specific sub-model (e.g. `cfg.aliyun`) as the sole
  constructor argument. `prefix` lives on the sub-model and the adapter
  reads `self._prefix = cfg.aliyun.prefix` internally.
- `images_dir` is irrelevant for cloud backends; just ignore the parameter.
  The factory keeps it in the signature so call sites don't have to
  branch.

## 7. Adapter "do / don't" checklist for Lane P

DO:

- Accept the sub-config model as the only constructor arg (optionally plus a
  pre-built SDK client for DI in tests).
- Prefix the key inside every method (`save` / `url` / `delete` / `exists`)
  — never expect the caller to prefix.
- Catch SDK exceptions and re-raise as
  `StorageError(provider="<name>", op="<save|url|delete|exists>", key=..., cause=exc)`.
- For `url`, branch on `self._public_base_url`. When empty, generate a
  presigned URL with TTL 3600 seconds.
- For `exists`, return `False` on a 404-equivalent error from the SDK;
  raise `StorageError` for any other failure.
- For `delete`, swallow `NoSuchKey` / 404 silently; raise `StorageError`
  for other failures. (`api/history.py` already wraps the call in a
  try/except `StorageError` → log → continue, so an adapter raising on
  network errors won't break DB deletion.)
- Use the SDK's own retry / backoff knobs where reasonable; do not invent
  your own retry loop.

DON'T:

- Write any state to disk.
- Log credentials, full presigned URLs, or `cause`'s formatted message
  blindly (truncate to 200 chars if you must).
- Re-export the SDK client outside the adapter.
- Modify `storage_backend.py`'s Protocol or `LocalBackend` — only the
  factory's dispatch table is yours to edit.
- Add a HEAD probe in `url()` to validate existence; `url()` is fast and
  side-effect-free.
- Catch broad `Exception:` — catch the SDK's specific exception types so
  bugs in adapter code surface normally.
