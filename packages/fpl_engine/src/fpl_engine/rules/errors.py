from __future__ import annotations


class RuleViolationError(ValueError):
    """Raised when a squad, transfer, or chip selection breaks an FPL rule."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
