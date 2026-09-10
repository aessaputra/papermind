"""
Custom exceptions and error handling for LangChain operations.

Provides specific exception types for retry logic and error handling.
"""



class RetryableError(Exception):
    """Base class for errors that should trigger retry logic."""


class RateLimitError(RetryableError):
    """Raised when API rate limit is exceeded."""


class APIError(RetryableError):
    """Raised when API returns a server error (5xx)."""


class TimeoutError(RetryableError):
    """Raised when API request times out."""


_retryable: list[type[Exception]] = [RetryableError, RateLimitError, APIError, TimeoutError]

# Try to import provider-specific exceptions
try:
    from anthropic import RateLimitError as AnthropicRateLimitError
    from anthropic import APIError as AnthropicAPIError
    _retryable.extend([AnthropicRateLimitError, AnthropicAPIError])
except ImportError:
    pass

try:
    from openai import RateLimitError as OpenAIRateLimitError
    from openai import APIError as OpenAIAPIError
    _retryable.extend([OpenAIRateLimitError, OpenAIAPIError])
except ImportError:
    pass

try:
    from google.api_core.exceptions import ResourceExhausted
    from google.api_core.exceptions import ServiceUnavailable
    _retryable.extend([ResourceExhausted, ServiceUnavailable])
except ImportError:
    pass

RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = tuple(_retryable)


def get_retryable_exceptions() -> tuple[type[Exception], ...]:
    """Back-compat alias — prefer RETRYABLE_EXCEPTIONS."""
    return RETRYABLE_EXCEPTIONS
