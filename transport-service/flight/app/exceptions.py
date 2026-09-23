"""
Custom exceptions for the Flight Service.
"""


class FlightServiceError(Exception):
    """Base exception for all flight service errors."""
    pass


class AirportNotFoundError(FlightServiceError):
    """Raised when an origin or destination airport/city cannot be resolved to an IATA code."""
    pass


class InvalidFlightRequestError(FlightServiceError):
    """Raised when the search parameters are semantically invalid."""
    pass


class ProviderTimeoutError(FlightServiceError):
    """Raised when the upstream flight provider times out."""
    pass


class ProviderAuthenticationError(FlightServiceError):
    """Raised when the upstream flight provider fails authentication (e.g. missing API key)."""
    pass


class ProviderAPIError(FlightServiceError):
    """Raised when the upstream flight provider returns an error payload or unexpected status."""
    pass
