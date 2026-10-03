# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

"""Exceptions raised by the Chronicle client."""

from __future__ import annotations

__all__ = [
    "AppendFailedError",
    "ChronicleError",
    "CommandFailedError",
    "TokenAuthorizationError",
    "TokenError",
    "TokenRequestError",
    "TokenResponseError",
]


class ChronicleError(Exception):
    """Base class for every error the client raises on its own behalf.

    Messages never contain the client secret or an access token.
    """


class CommandFailedError(ChronicleError):
    """The kernel answered a command with a failure result."""

    def __init__(self, operation: str, reasons: list[str]) -> None:
        self.operation = operation
        self.reasons = reasons
        super().__init__(f"{operation} failed: {'; '.join(reasons) if reasons else 'no reason given'}")


class AppendFailedError(ChronicleError):
    """The kernel did not append the event: it reported errors, a constraint violation or a concurrency violation."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__(f"The event was not appended: {'; '.join(reasons) if reasons else 'no reason given'}")


class TokenError(ChronicleError):
    """Base class for failures to obtain an access token."""


class TokenRequestError(TokenError):
    """The token request could not be completed: a network, TLS or timeout failure, or an unexpected HTTP status."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        self.status = status
        super().__init__(message)


class TokenAuthorizationError(TokenError):
    """The token endpoint rejected the client credentials, for example with an OAuth ``invalid_client`` error."""

    def __init__(self, status: int, error: str | None, description: str | None) -> None:
        self.status = status
        self.error = error
        self.description = description
        detail = ": ".join(part for part in (error, description) if part)
        super().__init__(
            f"The token endpoint rejected the client credentials (HTTP {status}){': ' + detail if detail else ''}"
        )


class TokenResponseError(TokenError):
    """The token endpoint answered successfully but the response is not a usable token response."""
