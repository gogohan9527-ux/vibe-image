"""Provider abstraction: dataclasses + Protocol shared by all upstreams.

A Provider is a thin object that knows three things:

* what credentials to ask the user for (``credential_fields``);
* how to fetch the list of models a key has access to;
* how to translate a ``GeneratorTask`` into an HTTP request and the upstream
  response back into a normalized ``ParsedResult``.

The dispatch (actually performing the HTTP call) lives in
``app.core.generator``; providers stay pure-data so they're trivial to mock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol


MultipartFile = tuple[str, bytes, str]
MultipartFiles = dict[str, MultipartFile] | list[tuple[str, MultipartFile]]


@dataclass
class CredField:
    """One credential field a Provider asks the user for."""

    name: str
    label: str
    secret: bool = True
    required: bool = True


@dataclass
class ModelInfo:
    id: str
    display_name: Optional[str] = None
    raw: Optional[dict] = None


@dataclass
class HttpCall:
    """Description of an upstream HTTP request the generator should make.

    For multipart (e.g. img2img) calls, set ``files`` and (optionally) ``data``
    instead of ``json_body``. ``files`` and ``json_body`` are mutually
    exclusive — the dispatcher picks the correct branch by checking which is
    non-None. When ``files`` is set, callers MUST NOT add a manual
    ``Content-Type`` header; ``requests`` generates the multipart boundary.
    """

    url: str
    method: str  # "GET" | "POST"
    headers: dict[str, str] = field(default_factory=dict)
    json_body: Optional[dict] = None
    # name -> (filename, content_bytes, mimetype), or a list of repeated
    # fields for providers that accept multiple files under the same name.
    files: Optional[MultipartFiles] = None
    # multipart plain text fields (str values; ints must be stringified)
    data: Optional[dict[str, str]] = None


@dataclass
class ParsedResult:
    """Normalized output of ``Provider.parse_response``."""

    image_url: Optional[str] = None
    image_bytes: Optional[bytes] = None
    revised_prompt: Optional[str] = None


class Provider(Protocol):
    """Each Provider exposes the same surface; see module docstring."""

    id: str
    display_name: str
    credential_fields: list[CredField]
    default_base_url: str
    # Whether this provider supports image-to-image generation. Implementations
    # that set this to True MUST also implement ``build_image_edit_request``;
    # the generator dispatch checks both before routing an img2img task here.
    supports_image_input: bool

    def list_models(
        self, creds: dict, base_url: str, timeout: int
    ) -> list[ModelInfo]:
        ...

    def build_request(
        self,
        task: "GeneratorTask",  # noqa: F821 - forward ref to avoid circular import
        creds: dict,
        base_url: str,
        model: str,
    ) -> HttpCall:
        ...

    def parse_response(self, resp_json: dict) -> ParsedResult:
        ...
