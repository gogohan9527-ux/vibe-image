"""Custom exceptions for the vibe-image backend."""

from __future__ import annotations


class VibeError(Exception):
    """Base error for all vibe-image business exceptions."""

    code: str = "vibe_error"
    http_status: int = 500

    def __init__(self, message: str = "", **extra: object) -> None:
        super().__init__(message or self.code)
        self.message = message or self.code
        self.extra = extra

    def to_payload(self) -> dict:
        payload: dict = {"code": self.code, "message": self.message}
        payload.update(self.extra)
        return payload


class QueueFullError(VibeError):
    code = "queue_full"
    http_status = 429

    def __init__(self, queue_size: int, cap: int) -> None:
        super().__init__(
            message=f"Queue is full ({queue_size}/{cap}).",
            queue_size=queue_size,
            cap=cap,
        )
        self.queue_size = queue_size
        self.cap = cap


class TaskNotFoundError(VibeError):
    code = "task_not_found"
    http_status = 404


class TaskNotCancellableError(VibeError):
    code = "task_not_cancellable"
    http_status = 409


class PromptNotFoundError(VibeError):
    code = "prompt_not_found"
    http_status = 404


class PromptConflictError(VibeError):
    code = "prompt_conflict"
    http_status = 409


class OutOfRangeError(VibeError):
    code = "out_of_range"
    http_status = 400

    def __init__(self, field: str, message: str = "") -> None:
        super().__init__(
            message=message or f"{field} is out of allowed range.",
            field=field,
        )
        self.field = field


class CancelledError(VibeError):
    """Raised by the generator when a cancel event was set."""

    code = "cancelled"
    http_status = 499  # client closed request, internal use only


class UpstreamError(VibeError):
    code = "upstream_error"
    http_status = 502


class CredentialDecryptError(VibeError):
    code = "credential_decrypt_failed"
    http_status = 400


class MissingApiKeyError(VibeError):
    code = "api_key_missing"
    http_status = 400


class UnknownProviderError(VibeError):
    code = "unknown_provider"
    http_status = 400

    def __init__(self, provider_id: str) -> None:
        super().__init__(
            message=f"unknown provider: {provider_id}", provider_id=provider_id
        )
        self.provider_id = provider_id


class ProviderNotConfiguredError(VibeError):
    code = "provider_not_configured"
    http_status = 400

    def __init__(self, provider_id: str, message: str = "") -> None:
        super().__init__(
            message=message or f"provider {provider_id} has no key configured",
            provider_id=provider_id,
        )
        self.provider_id = provider_id


class KeyNotFoundError(VibeError):
    code = "key_not_found"
    http_status = 400

    def __init__(self, key_id: str, http_status: int | None = None) -> None:
        super().__init__(message=f"key not found: {key_id}", key_id=key_id)
        self.key_id = key_id
        if http_status is not None:
            self.http_status = http_status


class InvalidCredentialsError(VibeError):
    code = "invalid_credentials"
    http_status = 400

    def __init__(self, missing_fields: list[str]) -> None:
        super().__init__(
            message=f"missing required credential fields: {missing_fields}",
            missing_fields=missing_fields,
        )
        self.missing_fields = missing_fields


class ProviderCapabilityError(VibeError):
    """Provider lacks a capability the task requires (e.g. image_input)."""

    code = "provider_capability_unsupported"
    http_status = 400

    def __init__(self, provider_id: str, capability: str) -> None:
        super().__init__(
            message=f"provider {provider_id} does not support capability: {capability}",
            provider_id=provider_id,
            capability=capability,
        )
        self.provider_id = provider_id
        self.capability = capability


class InvalidUploadError(VibeError):
    """Uploaded file did not pass MIME / header validation."""

    code = "invalid_upload"
    http_status = 400

    def __init__(self, reason: str) -> None:
        super().__init__(message=f"invalid upload: {reason}", reason=reason)
        self.reason = reason


class UploadTooLargeError(VibeError):
    """Uploaded file exceeded the configured ``max_upload_bytes``."""

    code = "upload_too_large"
    http_status = 413

    def __init__(self, max_bytes: int, actual_bytes: int) -> None:
        super().__init__(
            message=f"upload exceeds limit ({actual_bytes} > {max_bytes} bytes)",
            max_bytes=max_bytes,
            actual_bytes=actual_bytes,
        )
        self.max_bytes = max_bytes
        self.actual_bytes = actual_bytes


class InputImageNotFoundError(VibeError):
    """Referenced input image is missing or escapes images_dir."""

    code = "input_image_not_found"
    http_status = 400

    def __init__(self, input_image_path: str) -> None:
        super().__init__(
            message=f"input image not found: {input_image_path}",
            input_image_path=input_image_path,
        )
        self.input_image_path = input_image_path


class InputImageConflictError(VibeError):
    """Both legacy and multi-image request fields were supplied differently."""

    code = "input_image_conflict"
    http_status = 400

    def __init__(self) -> None:
        super().__init__(
            message="input_image_path conflicts with input_image_paths"
        )
