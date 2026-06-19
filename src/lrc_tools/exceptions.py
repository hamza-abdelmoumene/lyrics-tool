class LyricsToolError(Exception):
    """Base class for all lyrics-tool exceptions."""
    pass

class PlayerUnavailableError(LyricsToolError):
    """Raised when the requested media player cannot be found or accessed."""
    pass

class NetworkError(LyricsToolError):
    """Raised when a network request to LRCLIB or other sources fails."""
    pass

class MalformedLRCError(LyricsToolError):
    """Raised when an LRC file is severely malformed or empty."""
    pass
