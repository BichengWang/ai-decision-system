"""Exceptions raised by the decision model."""


class DecisionError(Exception):
    """Base class for every error this package raises."""


class QuestionError(DecisionError, ValueError):
    """A question or question set is invalid; raised before any request is sent."""


class ResponseError(DecisionError):
    """A provider response does not match the questions that were asked."""


class APIError(DecisionError):
    """The provider returned an HTTP error or could not be reached."""

    def __init__(self, message, status=None, body=None):
        super().__init__(message)
        self.status = status
        self.body = body

    @property
    def retryable(self):
        return self.status is None or self.status == 429 or self.status >= 500
