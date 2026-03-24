class IngestionError(Exception):
    """Raised when a file cannot be ingested (missing, unreadable, or invalid)."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"IngestionError: {path!r} — {reason}")


class GLPIUnavailableError(Exception):
    """Raised when the GLPI proxy is unreachable or returns an unrecoverable error."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class LLMUnavailableError(Exception):
    """Raised when the LLM provider is unavailable or returns an unrecoverable error."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
