class RazorpayServiceError(Exception):
    """Base exception for all Razorpay integration failures."""


class RazorpayAuthError(RazorpayServiceError):
    """Raised when API credentials are invalid or expired."""


class RazorpayRateLimitError(RazorpayServiceError):
    """Raised when Razorpay rate limits the request."""


class RazorpayTimeoutError(RazorpayServiceError):
    """Raised when a request to Razorpay times out."""


class RazorpayNotFoundError(RazorpayServiceError):
    """Raised when a requested resource (payment/order/refund/settlement) doesn't exist."""


class RazorpayMalformedResponseError(RazorpayServiceError):
    """Raised when Razorpay returns a response that doesn't match the expected shape."""
