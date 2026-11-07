class JetraError(Exception):
    """Base exception for all Jetra errors."""
    pass

class JetraConnectionError(JetraError):
    """Raised when connection to the server is lost."""
    pass

class JetraRPCError(JetraError):
    """Raised when the server returns an RPC error (e.g., NOT_IMPLEMENTED, FLOOD_WAIT)."""
    def __init__(self, message, method=None):
        super().__init__(message)
        self.method = method

class JetraAuthError(JetraError):
    """Raised when authentication fails or session is invalid."""
    pass
