class ExternalServiceError(RuntimeError):
    """Raised when external data providers are unavailable or return invalid data."""


class DataMappingError(ValueError):
    """Raised when external payload values cannot be mapped to domain types."""
