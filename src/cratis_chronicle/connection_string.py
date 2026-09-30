# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

"""Parsing and validation of ``chronicle://`` connection strings.

Parsing only describes the endpoint and the authentication mode. It never opens a connection or fetches a token.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, quote, unquote, urlsplit

__all__ = [
    "AmbiguousAuthenticationError",
    "ChronicleConnectionOptions",
    "ConnectionStringError",
    "DEFAULT_PORT",
    "IncompleteCredentialsError",
    "InvalidCredentialsEncodingError",
    "InvalidHostError",
    "InvalidPortError",
    "MalformedConnectionStringError",
    "MissingHostError",
    "UnsupportedOptionError",
    "UnsupportedSchemeError",
    "parse_connection_string",
]

DEFAULT_PORT = 35000

_SCHEME = "chronicle"
_REDACTED = "****"
_HOST_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
_PORT = re.compile(r"^[0-9]+$")
# Query parameters that select an authentication mode. They may not be combined with client credentials.
_AUTHENTICATION_PARAMETERS = frozenset({"apikey", "auth"})


class ConnectionStringError(ValueError):
    """Base class for every error raised while parsing a Chronicle connection string."""


class MalformedConnectionStringError(ConnectionStringError):
    """The connection string is not structurally valid, for example it contains whitespace."""


class UnsupportedSchemeError(ConnectionStringError):
    """The scheme is not ``chronicle``."""


class MissingHostError(ConnectionStringError):
    """The connection string names no host."""


class InvalidHostError(ConnectionStringError):
    """The host is not a valid host name or IP address, or more than one host was given."""


class InvalidPortError(ConnectionStringError):
    """The port is not an integer between 1 and 65535."""


class IncompleteCredentialsError(ConnectionStringError):
    """The client id or the client secret is missing or empty."""


class InvalidCredentialsEncodingError(ConnectionStringError):
    """The client id or the client secret contains percent-encoding that is not valid UTF-8."""


class AmbiguousAuthenticationError(ConnectionStringError):
    """Client credentials are combined with another authentication selector such as ``apiKey`` or ``auth``."""


class UnsupportedOptionError(ConnectionStringError):
    """The connection string uses a path, fragment or query parameter this client does not support yet."""


@dataclass(frozen=True, slots=True)
class ChronicleConnectionOptions:
    """Immutable options describing how to reach a Chronicle kernel with client credentials.

    The client secret is excluded from ``repr()`` and ``str()`` so it cannot leak into logs or error messages.
    """

    host: str
    """The host name or IP address of the kernel, without brackets for IPv6 addresses."""

    client_id: str
    """The decoded OAuth client id."""

    client_secret: str = field(repr=False)
    """The decoded OAuth client secret."""

    port: int = DEFAULT_PORT
    """The port of the kernel. Defaults to 35000."""

    tls: bool = True
    """Whether the connection to the kernel uses TLS. Direct kernel connections always default to TLS."""

    @classmethod
    def parse(cls, connection_string: str) -> ChronicleConnectionOptions:
        """Parse a ``chronicle://`` connection string. See :func:`parse_connection_string`."""
        return parse_connection_string(connection_string)

    def __str__(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{_SCHEME}://{quote(self.client_id, safe='')}:{_REDACTED}@{host}:{self.port}"


def parse_connection_string(connection_string: str) -> ChronicleConnectionOptions:
    """Parse ``chronicle://<client-id>:<client-secret>@<host>[:<port>]`` into immutable options.

    The client id and secret are percent-decoded. The port defaults to 35000 and TLS is on. A trailing ``/`` is
    accepted. Nothing else is: multiple hosts, ``chronicle+srv``, and every query parameter are rejected, so
    behavior that is not designed yet is never silently ignored.

    Raises:
        TypeError: ``connection_string`` is not a ``str``.
        MalformedConnectionStringError: The string contains whitespace or control characters.
        UnsupportedSchemeError: The scheme is not ``chronicle``.
        MissingHostError: No host is given.
        InvalidHostError: The host is invalid, or more than one host is given.
        InvalidPortError: The port is not an integer between 1 and 65535.
        AmbiguousAuthenticationError: Credentials are combined with ``apiKey`` or ``auth``.
        UnsupportedOptionError: A path, fragment, or query parameter is given that is not supported yet.
        IncompleteCredentialsError: The client id or the client secret is missing or empty.
        InvalidCredentialsEncodingError: The credentials are not valid percent-encoded UTF-8.
    """
    if not isinstance(connection_string, str):
        raise TypeError(f"A connection string must be a str, not {type(connection_string).__name__}")

    if any(ord(character) <= 0x20 or ord(character) == 0x7F for character in connection_string):
        raise MalformedConnectionStringError("The connection string must not contain whitespace or control characters")

    scheme, separator, _ = connection_string.partition("://")
    if not separator or scheme.lower() != _SCHEME:
        raise UnsupportedSchemeError(f"The connection string scheme must be '{_SCHEME}://'")

    try:
        parts = urlsplit(connection_string)
    except ValueError as error:
        raise MalformedConnectionStringError("The connection string is not a valid URL") from error

    user_info, has_user_info, host_and_port = parts.netloc.rpartition("@")
    host, port = _parse_host_and_port(host_and_port)

    if parts.path not in ("", "/"):
        raise UnsupportedOptionError("A path other than '/' is not supported")
    if parts.fragment or connection_string.endswith("#"):
        raise UnsupportedOptionError("A fragment is not supported")
    _validate_query(parts.query, has_credentials=bool(has_user_info))

    client_id, client_secret = _parse_credentials(user_info, has_user_info=bool(has_user_info))
    return ChronicleConnectionOptions(host=host, client_id=client_id, client_secret=client_secret, port=port)


def _parse_host_and_port(host_and_port: str) -> tuple[str, int]:
    if host_and_port.startswith("["):
        closing = host_and_port.find("]")
        if closing == -1:
            raise InvalidHostError("An IPv6 address must be closed with ']'")
        host = host_and_port[1:closing]
        remainder = host_and_port[closing + 1 :]
        if remainder and not remainder.startswith(":"):
            raise InvalidHostError("Unexpected text after the IPv6 address")
        port_text = remainder[1:] if remainder else None
        try:
            ipaddress.IPv6Address(host)
        except ValueError as error:
            raise InvalidHostError("The bracketed host is not a valid IPv6 address") from error
    else:
        if "," in host_and_port:
            raise InvalidHostError("Multiple hosts are not supported")
        if host_and_port.count(":") > 1:
            raise InvalidHostError("An IPv6 address must be enclosed in brackets")
        host, has_port, port_text_value = host_and_port.partition(":")
        port_text = port_text_value if has_port else None
        if not host:
            raise MissingHostError("The connection string does not name a host")
        if not _HOST_NAME.match(host):
            raise InvalidHostError("The host contains characters that are not valid in a host name")

    return host, _parse_port(port_text)


def _parse_port(port_text: str | None) -> int:
    if port_text is None:
        return DEFAULT_PORT
    if not _PORT.match(port_text):
        raise InvalidPortError("The port must be an integer between 1 and 65535")
    port = int(port_text)
    if not 1 <= port <= 65535:
        raise InvalidPortError("The port must be an integer between 1 and 65535")
    return port


def _validate_query(query: str, *, has_credentials: bool) -> None:
    if not query:
        return

    names = [name for name, _ in parse_qsl(query, keep_blank_values=True)]
    if not names:
        raise UnsupportedOptionError("An empty query string is not supported")

    if has_credentials:
        selectors = sorted(name for name in names if name.casefold() in _AUTHENTICATION_PARAMETERS)
        if selectors:
            raise AmbiguousAuthenticationError(
                f"Client credentials cannot be combined with the '{selectors[0]}' authentication option"
            )

    raise UnsupportedOptionError(f"The query parameter '{names[0]}' is not supported yet")


def _parse_credentials(user_info: str, *, has_user_info: bool) -> tuple[str, str]:
    if not has_user_info:
        raise IncompleteCredentialsError("The connection string must contain a client id and a client secret")

    raw_client_id, separator, raw_client_secret = user_info.partition(":")
    if not separator or not raw_client_id or not raw_client_secret:
        raise IncompleteCredentialsError("Both a client id and a client secret are required")

    try:
        return unquote(raw_client_id, errors="strict"), unquote(raw_client_secret, errors="strict")
    except UnicodeDecodeError as error:
        raise InvalidCredentialsEncodingError("The credentials are not valid percent-encoded UTF-8") from error
