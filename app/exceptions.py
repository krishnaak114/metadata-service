"""
Custom application exceptions.

Using distinct exception types lets routers map them to the right HTTP status
codes without resorting to string-matching on messages.
"""


class NotFoundError(ValueError):
    """Raised when a requested resource does not exist."""


class ConflictError(ValueError):
    """Raised when the operation would violate a uniqueness constraint."""


class CycleError(ValueError):
    """Raised when a lineage edge would create a cycle in the DAG."""
