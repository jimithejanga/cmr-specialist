"""Registry error types: the module's envelope mapping (terminal vs transient)
is identical no matter which database answers. (Moved here from the retired
dict backend so the contract outlives the implementation.)"""


class TransientError(Exception):
    """Retryable: timeout, 5xx, rate-limit."""


class TerminalError(Exception):
    """Not retryable: not-found, validation, forbidden."""
