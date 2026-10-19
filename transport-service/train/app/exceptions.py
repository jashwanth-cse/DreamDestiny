class StationNotFoundError(Exception):
    """Raised when a requested station cannot be found."""
    pass

class InvalidRequestError(Exception):
    """Raised when the request parameters are invalid."""
    pass

class UpstreamTimeoutError(Exception):
    """Raised when the upstream provider times out."""
    pass

class UpstreamConnectionError(Exception):
    """Raised when connection to the upstream provider fails."""
    pass

class UpstreamServiceError(Exception):
    """Raised when the upstream provider returns an unrecoverable 5xx error."""
    pass

class CircuitBreakerOpenError(Exception):
    """Raised when the circuit breaker is open due to consecutive upstream failures."""
    pass

class TrainNotFoundError(Exception):
    """Raised when the requested train does not exist or has no schedule for the route."""
    pass
