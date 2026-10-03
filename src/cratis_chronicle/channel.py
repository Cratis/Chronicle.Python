# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

"""The authenticated gRPC channel. Token acquisition stays in the token provider; the channel only asks it per call."""

from __future__ import annotations

import grpc
from grpc import aio

from .connection_string import ChronicleConnectionOptions
from .errors import InsecureTransportError
from .http_transport import StreamFormTransport, TokenTransport
from .tls import is_loopback_host, resolve_tls_trust
from .token_provider import OAuthTokenProvider

__all__ = ["BearerTokenInterceptor", "ChronicleChannel"]


def _with_bearer(details: aio.ClientCallDetails, token: str) -> aio.ClientCallDetails:
    metadata = aio.Metadata(*(details.metadata or ()))
    metadata.add("authorization", f"Bearer {token}")
    return aio.ClientCallDetails(details.method, details.timeout, metadata, details.credentials, details.wait_for_ready)


class BearerTokenInterceptor(aio.UnaryUnaryClientInterceptor, aio.UnaryStreamClientInterceptor):  # type: ignore[misc]
    """Adds ``authorization: Bearer <token>`` to every new call with the provider's current token.

    The token is looked up when each call starts, never baked into the channel, so refreshes take effect on the next
    call. A token failure surfaces as the provider's ``TokenError``.
    """

    def __init__(self, provider: OAuthTokenProvider) -> None:
        self._provider = provider

    async def intercept_unary_unary(self, continuation, client_call_details, request):  # type: ignore[no-untyped-def]
        return await continuation(_with_bearer(client_call_details, await self._provider.get_token()), request)

    async def intercept_unary_stream(self, continuation, client_call_details, request):  # type: ignore[no-untyped-def]
        return await continuation(_with_bearer(client_call_details, await self._provider.get_token()), request)


class ChronicleChannel:
    """Owns the gRPC channel and the token provider and closes both deterministically."""

    def __init__(self, channel: aio.Channel, provider: OAuthTokenProvider) -> None:
        self._channel = channel
        self._provider = provider
        self._closed = False

    @property
    def channel(self) -> aio.Channel:
        """The underlying authenticated ``grpc.aio`` channel, for generated stubs."""
        return self._channel

    @classmethod
    async def open(
        cls,
        options: ChronicleConnectionOptions,
        *,
        ca_certificates: bytes | None = None,
        token_transport: TokenTransport | None = None,
    ) -> ChronicleChannel:
        """Create the channel for ``options``. Nothing is sent until the first call; the first call fetches a token."""
        if not options.tls and not is_loopback_host(options.host):
            raise InsecureTransportError(
                "Client credentials and access tokens are not sent without TLS to a host other than localhost"
            )
        trust = await resolve_tls_trust(options, ca_certificates=ca_certificates)
        transport = token_transport or StreamFormTransport(trust.ssl_context() if trust else None)
        provider = OAuthTokenProvider(options, transport)
        target = f"{options.host}:{options.port}" if ":" not in options.host else f"[{options.host}]:{options.port}"
        interceptors = [BearerTokenInterceptor(provider)]
        if trust is None:
            channel = aio.insecure_channel(target, interceptors=interceptors)
        else:
            credentials = grpc.ssl_channel_credentials(root_certificates=trust.root_certificates)
            channel = aio.secure_channel(target, credentials, interceptors=interceptors)
        return cls(channel, provider)

    async def aclose(self) -> None:
        """Close the channel and the token provider. Safe to call more than once."""
        if self._closed:
            return
        self._closed = True
        try:
            await self._channel.close()
        finally:
            await self._provider.aclose()

    async def __aenter__(self) -> ChronicleChannel:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
