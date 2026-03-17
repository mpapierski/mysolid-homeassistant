from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class AuthErrorDetails:
    error_code: int | None = None
    lock_time_ms: int | None = None


class MySolidError(Exception):
    """Base exception for the MySolid client."""


class MySolidSessionError(MySolidError):
    """Raised when an authenticated endpoint is called without a session."""


class MySolidApiError(MySolidError):
    """Raised when the MySolid API returns a non-success response."""

    def __init__(
        self,
        status: int,
        message: str,
        *,
        payload: Any | None = None,
    ) -> None:
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message
        self.payload = payload


class MySolidAuthError(MySolidApiError):
    """Raised when authentication or authorization fails."""

    def __init__(
        self,
        status: int,
        message: str,
        *,
        payload: Any | None = None,
        details: AuthErrorDetails | None = None,
    ) -> None:
        super().__init__(status, message, payload=payload)
        self.details = details or AuthErrorDetails()
