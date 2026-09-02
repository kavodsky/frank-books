"""Classified failures. `error_class` is set at raise time (roadmap 0.5.1)."""

from __future__ import annotations

from enum import StrEnum


class ErrorClass(StrEnum):
    MODEL_UNREACHABLE = "model_unreachable"
    TIMEOUT = "timeout"
    SCHEMA_INVALID = "schema_invalid"
    VALIDATION_EXHAUSTED = "validation_exhausted"
    DB_ERROR = "db_error"
    TERMBASE_NOT_APPROVED = "termbase_not_approved"
    UNKNOWN = "unknown"


class FrankError(Exception):
    """Root of the domain error hierarchy. Every subclass pins an ErrorClass."""

    error_class: ErrorClass

    def __init__(self, message: str, error_class: ErrorClass) -> None:
        super().__init__(message)
        self.message = message
        self.error_class = error_class


class ModelUnreachable(FrankError):
    def __init__(self, message: str) -> None:
        super().__init__(message, ErrorClass.MODEL_UNREACHABLE)


class ModelTimeout(FrankError):
    def __init__(self, message: str) -> None:
        super().__init__(message, ErrorClass.TIMEOUT)


class SchemaInvalid(FrankError):
    def __init__(self, message: str) -> None:
        super().__init__(message, ErrorClass.SCHEMA_INVALID)


class ValidationExhausted(FrankError):
    def __init__(self, message: str) -> None:
        super().__init__(message, ErrorClass.VALIDATION_EXHAUSTED)


class DbError(FrankError):
    def __init__(self, message: str) -> None:
        super().__init__(message, ErrorClass.DB_ERROR)


class TermbaseNotApproved(FrankError):
    def __init__(self, message: str) -> None:
        super().__init__(message, ErrorClass.TERMBASE_NOT_APPROVED)


class UnknownError(FrankError):
    def __init__(self, message: str) -> None:
        super().__init__(message, ErrorClass.UNKNOWN)
