# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

"""Experimental Python client for Cratis Chronicle."""

from importlib.metadata import PackageNotFoundError, version

from .channel import BearerTokenInterceptor, ChronicleChannel
from .client import DEFAULT_NAMESPACE, EVENT_LOG, ChronicleClient, EventSequence, EventStore, Namespace
from .connection_string import (
    DEFAULT_PORT,
    DEVELOPMENT_CLIENT_ID,
    DEVELOPMENT_CLIENT_SECRET,
    AmbiguousAuthenticationError,
    ChronicleConnectionOptions,
    ConnectionStringError,
    IncompleteCredentialsError,
    InvalidCredentialsEncodingError,
    InvalidHostError,
    InvalidPortError,
    MalformedConnectionStringError,
    MissingHostError,
    UnsupportedOptionError,
    UnsupportedSchemeError,
    parse_connection_string,
)
from .errors import (
    AppendFailedError,
    ChronicleError,
    CommandFailedError,
    InsecureTransportError,
    TokenAuthorizationError,
    TokenError,
    TokenRequestError,
    TokenResponseError,
)
from .events import AppendResult, EventTypeDefinition
from .http_transport import HttpResponse, StreamFormTransport, TokenTransport
from .tls import TlsTrust, is_loopback_host, resolve_tls_trust
from .token_provider import DEFAULT_TOKEN_LIFETIME_SECONDS, OAuthTokenProvider
from .wire import ConceptAs

try:
    __version__ = version("cratis-chronicle")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "DEFAULT_NAMESPACE",
    "EVENT_LOG",
    "DEFAULT_TOKEN_LIFETIME_SECONDS",
    "AppendFailedError",
    "AppendResult",
    "BearerTokenInterceptor",
    "ChronicleChannel",
    "ChronicleClient",
    "ChronicleError",
    "CommandFailedError",
    "ConceptAs",
    "EventSequence",
    "EventStore",
    "EventTypeDefinition",
    "HttpResponse",
    "Namespace",
    "OAuthTokenProvider",
    "StreamFormTransport",
    "TlsTrust",
    "TokenAuthorizationError",
    "InsecureTransportError",
    "TokenError",
    "TokenRequestError",
    "TokenResponseError",
    "TokenTransport",
    "is_loopback_host",
    "resolve_tls_trust",
    "DEFAULT_PORT",
    "DEVELOPMENT_CLIENT_ID",
    "DEVELOPMENT_CLIENT_SECRET",
    "AmbiguousAuthenticationError",
    "ChronicleConnectionOptions",
    "ConnectionStringError",
    "IncompleteCredentialsError",
    "InvalidCredentialsEncodingError",
    "InvalidHostError",
    "InvalidPortError",
    "MalformedConnectionStringError",
    "MissingHostError",
    "UnsupportedOptionError",
    "UnsupportedSchemeError",
    "__version__",
    "parse_connection_string",
]
