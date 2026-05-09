"""MOMO Provider: OpenAI-compatible image generation upstream.

Endpoints:

* ``GET  {base_url}/models``               — list_models
* ``POST {base_url}/images/generations``    — generation

The provider is pure-data: it never touches the global config or the global
``requests`` session for outbound calls except inside ``list_models``, which
must stay synchronous so the ``add_key`` API can use it inline.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import requests

from ..errors import UpstreamError
from .base import CredField, HttpCall, ModelInfo, ParsedResult


if TYPE_CHECKING:
    from ..core.generator import GeneratorTask


def _summary(text: str, n: int = 200) -> str:
    text = text or ""
    return text[:n] + ("..." if len(text) > n else "")


_MIME_BY_SUFFIX: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class MomoProvider:
    id = "momo"
    display_name = "MOMO"
    default_base_url = "https://momoapi.top/v1"
    # 2026-05-09 Addendum (II) — img2img is supported via /images/edits.
    supports_image_input = True

    def __init__(self) -> None:
        self.credential_fields: list[CredField] = [
            CredField(name="api_key", label="API Key", secret=True, required=True),
        ]

    # ---------- list_models ----------

    def list_models(
        self, creds: dict, base_url: str, timeout: int
    ) -> list[ModelInfo]:
        api_key = creds.get("api_key")
        if not api_key:
            raise UpstreamError("missing api_key in credentials")
        url = f"{base_url.rstrip('/')}/models"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            raise UpstreamError(f"list_models request failed: {exc}") from exc
        if resp.status_code >= 400:
            raise UpstreamError(
                f"list_models HTTP {resp.status_code}: {_summary(resp.text)}"
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise UpstreamError(
                f"list_models returned non-JSON: {_summary(resp.text)}"
            ) from exc
        items = payload.get("data") or []
        if not isinstance(items, list):
            raise UpstreamError("list_models payload missing 'data' array")
        out: list[ModelInfo] = []
        for entry in items:
            if not isinstance(entry, dict):
                continue
            mid = entry.get("id")
            if not isinstance(mid, str) or not mid:
                continue
            out.append(ModelInfo(id=mid, display_name=None, raw=entry))
        return out

    # ---------- build_request / parse_response ----------

    def build_request(
        self,
        task: "GeneratorTask",
        creds: dict,
        base_url: str,
        model: str,
    ) -> HttpCall:
        api_key = creds.get("api_key", "")
        url = f"{base_url.rstrip('/')}/images/generations"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "prompt": task.prompt,
            "n": 1,
            "size": task.size,
            "quality": task.quality,
            "format": task.format,
        }
        return HttpCall(url=url, method="POST", headers=headers, json_body=body)

    def build_image_edit_request(
        self,
        task: "GeneratorTask",
        creds: dict,
        base_url: str,
        model: str,
    ) -> HttpCall:
        """Build a multipart POST to ``/images/edits`` (OpenAI-compatible).

        ``task.input_image_path`` MUST be a non-None ``Path`` pointing at an
        existing PNG/JPEG/WEBP file. Caller (``app.core.generator``) is
        responsible for that pre-condition.

        TODO: ``quality`` / ``format`` are intentionally omitted from the
        edits payload — OpenAI's edits endpoint rejects them. If MOMO accepts
        them they could be added here later.
        """
        if task.input_image_path is None:
            raise ValueError("build_image_edit_request requires task.input_image_path")
        api_key = creds.get("api_key", "")
        url = f"{base_url.rstrip('/')}/images/edits"
        suffix = task.input_image_path.suffix.lower()
        mimetype = _MIME_BY_SUFFIX.get(suffix, "application/octet-stream")
        content = task.input_image_path.read_bytes()
        # Use only the suffix-bearing filename; do NOT leak server fs paths.
        filename = task.input_image_path.name
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            # NB: Content-Type intentionally omitted — requests builds the
            # multipart boundary itself.
        }
        files = {"image": (filename, content, mimetype)}
        data = {
            "model": model,
            "prompt": task.prompt,
            "size": task.size,
            "n": "1",
        }
        return HttpCall(
            url=url, method="POST", headers=headers, files=files, data=data
        )

    def parse_response(self, resp_json: dict) -> ParsedResult:
        data = resp_json.get("data") or []
        if not data:
            raise UpstreamError(
                f"Upstream returned no data: {_summary(json.dumps(resp_json, ensure_ascii=False))}"
            )
        first = data[0] if isinstance(data, list) else {}
        url = first.get("url") if isinstance(first, dict) else None
        if not url:
            raise UpstreamError("Upstream response did not contain an image URL.")
        revised = None
        if isinstance(first, dict):
            cand = first.get("revised_prompt")
            if isinstance(cand, str) and cand.strip():
                revised = cand.strip()
        return ParsedResult(image_url=url, revised_prompt=revised)
