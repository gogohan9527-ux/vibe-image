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
