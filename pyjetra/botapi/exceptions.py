class JetraError(Exception):
    pass


class FileTooLargeError(JetraError):
    """Raised when a file exceeds the Jetra upload limit."""
    pass