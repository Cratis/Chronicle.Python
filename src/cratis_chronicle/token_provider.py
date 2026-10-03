# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

"""Async OAuth client-credentials token provider for Chronicle's ``/connect/token`` endpoint."""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .connection_string import ChronicleConnectionOptions
from .errors import TokenAuthorizationError, TokenRequestError, TokenResponseError
from .http_transport import HttpResponse, TokenTransport

__all__ = ["DEFAULT_TOKEN_LIFETIME_SECONDS", "OAuthTokenProvider", "TOKEN_PATH"]

TOKEN_PATH = "/connect/token"  # noqa: S105 - an endpoint path, not a secret
DEFAULT_TOKEN_LIFETIME_SECONDS = 30.0
"""The lifetime assumed when the endpoint omits ``expires_in``. Deliberately short so an unknown expiry is never trusted
for long."""

_MAX_REFRESH_MARGIN_SECONDS = 30.0
_REDACTED = "****"


@dataclass(frozen=True, slots=True)
class _CachedToken:
    value: str
    refresh_at: float


class OAuthTokenProvider:
    """Obtains, caches and refreshes the access token used for every new gRPC call.

    A token is reused until shortly before it expires. Concurrent callers share one in-flight request, and one caller
    being cancelled does not cancel the request the others wait for. The client secret and the token never appear in
    ``repr()``, ``str()`` or an exception message.
    """

    def __init__(
        self,
        options: ChronicleConnectionOptions,
        transport: TokenTransport,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client_id = options.client_id
        self._client_secret = options.client_secret
        self._url = f"{'https' if options.tls else 'http'}://{_authority(options)}{TOKEN_PATH}"
        self._transport = transport
        self._clock = clock
        self._token: _CachedToken | None = None
        self._refresh: asyncio.Task[_CachedToken] | None = None
        self._closed = False

    def __repr__(self) -> str:
        return f"OAuthTokenProvider(url={self._url!r}, client_id={self._client_id!r})"

    async def get_token(self) -> str:
        """Return a valid access token, requesting a new one when none is cached or it is about to expire.

        Raises:
            TokenAuthorizationError: The endpoint rejected the credentials.
            TokenResponseError: The endpoint returned an unusable response.
            TokenRequestError: The request failed or the provider is closed.
        """
        if self._closed:
            raise TokenRequestError("The token provider is closed")
        cached = self._token
        if cached is not None and self._clock() < cached.refresh_at:
            return cached.value
        if self._refresh is None or self._refresh.done():
            self._refresh = asyncio.ensure_future(self._request_token())
        # Shielded: cancelling this caller must not cancel the request other callers are waiting on.
        return (await asyncio.shield(self._refresh)).value

    def invalidate(self) -> None:
        """Forget the cached token so the next call requests a new one."""
        self._token = None

    async def aclose(self) -> None:
        """Cancel any in-flight request and refuse further use. Safe to call more than once."""
        self._closed = True
        self._token = None
        refresh, self._refresh = self._refresh, None
        if refresh is not None and not refresh.done():
            refresh.cancel()
        if refresh is not None:
            await asyncio.gather(refresh, return_exceptions=True)

    async def _request_token(self) -> _CachedToken:
        response = await self._transport.post_form(
            self._url,
            {"grant_type": "client_credentials", "client_id": self._client_id, "client_secret": self._client_secret},
        )
        token = self._interpret(response)
        if not self._closed:
            self._token = token
        return token

    def _interpret(self, response: HttpResponse) -> _CachedToken:
        if response.status in (400, 401, 403):
            error, description = self._read_oauth_error(response.body)
            raise TokenAuthorizationError(response.status, error, description)
        if not 200 <= response.status < 300:
            raise TokenRequestError(f"The token endpoint answered HTTP {response.status}", status=response.status)

        payload = self._parse_object(response.body)
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token.strip():
            raise TokenResponseError("The token response has no access_token")
        token_type = payload.get("token_type")
        if token_type is not None and (not isinstance(token_type, str) or token_type.lower() != "bearer"):
            raise TokenResponseError("The token response has a token_type other than Bearer")

        lifetime = DEFAULT_TOKEN_LIFETIME_SECONDS
        if "expires_in" in payload and payload["expires_in"] is not None:
            expires_in = payload["expires_in"]
            if (
                isinstance(expires_in, bool)
                or not isinstance(expires_in, int | float)
                or not math.isfinite(expires_in)
                or expires_in <= 0
            ):
                raise TokenResponseError("The token response has an invalid expires_in")
            lifetime = float(expires_in)
        margin = min(_MAX_REFRESH_MARGIN_SECONDS, lifetime / 2)
        return _CachedToken(value=access_token, refresh_at=self._clock() + lifetime - margin)

    def _parse_object(self, body: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError) as error:
            raise TokenResponseError("The token response is not valid JSON") from error
        if not isinstance(payload, dict):
            raise TokenResponseError("The token response is not a JSON object")
        return payload

    def _read_oauth_error(self, body: bytes) -> tuple[str | None, str | None]:
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return None, None
        if not isinstance(payload, dict):
            return None, None
        return self._scrub(payload.get("error")), self._scrub(payload.get("error_description"))

    def _scrub(self, value: object) -> str | None:
        if not isinstance(value, str):
            return None
        text = value[:200]
        if self._client_secret:
            text = text.replace(self._client_secret, _REDACTED)
        return text


def _authority(options: ChronicleConnectionOptions) -> str:
    host = f"[{options.host}]" if ":" in options.host else options.host
    return f"{host}:{options.port}"
