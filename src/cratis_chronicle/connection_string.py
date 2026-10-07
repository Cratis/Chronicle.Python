# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

"""Parsing and validation of ``chronicle://`` connection strings.

Parsing only describes the endpoint and the authentication mode. It never opens a connection or fetches a token.
The accepted grammar is a strict subset of the one Chronicle's .NET ``ChronicleConnectionStringBuilder`` accepts.
"""

from __future__ import annotations

import ipaddress
import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, quote, unquote, urlsplit

__all__ = [
    "AmbiguousAuthenticationError",
    "ChronicleConnectionOptions",
    "ConnectionStringError",
    "DEFAULT_PORT",
    "DEVELOPMENT_CLIENT_ID",
    "DEVELOPMENT_CLIENT_SECRET",
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
DEVELOPMENT_CLIENT_ID = "chronicle-dev-client"
"""The client id used when a connection string carries no credentials. It is a well-known development value."""

DEVELOPMENT_CLIENT_SECRET = "chronicle-dev-secret"  # noqa: S105 - a well-known development value, not a secret
"""The client secret used when a connection string carries no credentials. It is a well-known development value."""

_SCHEME = "chronicle"
_REDACTED = "****"
_HOST_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9_-]*[A-Za-z0-9])?")
_ZONE_ID = re.compile(r"[A-Za-z0-9._~-]+")
_FORBIDDEN_RAW_CATEGORIES = {"Cc", "Cf", "Cn", "Zs", "Zl", "Zp"}
_PORT = re.compile(r"^[0-9]+$")
_API_KEY = "apikey"
_AUTH = "auth"
_SKIP_TLS_VALIDATION = "skiptlsvalidation"
_BOOLEANS = {"true": True, "false": False}


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
    """Only one of the client id and the client secret is given, or one of them is empty."""


class InvalidCredentialsEncodingError(ConnectionStringError):
    """The client id or the client secret is not valid UTF-8, including lone Unicode surrogates."""


class AmbiguousAuthenticationError(ConnectionStringError):
    """Client credentials are combined with a non-empty ``apiKey``."""


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

    skip_tls_validation: bool = True
    """Whether the kernel certificate is accepted without validation. Defaults to ``True`` like the .NET client, so a
    development kernel with a self-signed certificate works. Set ``skipTlsValidation=false`` to require a verifiable
    certificate. TLS itself stays on either way."""

    @classmethod
    def parse(cls, connection_string: str) -> ChronicleConnectionOptions:
        """Parse a ``chronicle://`` connection string. See :func:`parse_connection_string`."""
        return parse_connection_string(connection_string)

    def __str__(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        suffix = "" if self.skip_tls_validation else "/?skipTlsValidation=false"
        return f"{_SCHEME}://{quote(self.client_id, safe='')}:{_REDACTED}@{host}:{self.port}{suffix}"


def parse_connection_string(connection_string: str) -> ChronicleConnectionOptions:
    """Parse ``chronicle://[<client-id>:<client-secret>@]<host>[:<port>][/][?skipTlsValidation=<bool>]``.

    The client id and secret are percent-decoded. A connection string without credentials uses the development
    credentials, so ``chronicle://localhost:35000`` equals
    ``chronicle://chronicle-dev-client:chronicle-dev-secret@localhost:35000``. A partial set of credentials is an
    error. The port defaults to 35000, TLS is on, and ``skipTlsValidation`` defaults to ``true`` like the .NET
    client. A trailing ``/`` is accepted, and so is an empty ``apiKey``, which is treated as absent. Nothing else is:
    multiple hosts, ``chronicle+srv``, a non-empty ``apiKey``, ``auth`` and every other query parameter are
    rejected, so behavior that is not designed yet is never silently ignored.

    Raises:
        TypeError: ``connection_string`` is not a ``str``.
        MalformedConnectionStringError: The raw string contains Unicode whitespace, control, format or unassigned
            characters.
        UnsupportedSchemeError: The scheme is not ``chronicle``.
        MissingHostError: No host is given.
        InvalidHostError: The host or its brackets are invalid, or more than one host is given.
        InvalidPortError: The port is not an integer between 1 and 65535.
        AmbiguousAuthenticationError: Credentials are combined with a non-empty ``apiKey``.
        UnsupportedOptionError: A path, fragment, or query parameter is given that is not supported yet, or
            ``skipTlsValidation`` is not ``true`` or ``false``.
        IncompleteCredentialsError: Only one of the client id and the client secret is given, or one is empty.
        InvalidCredentialsEncodingError: The credentials contain invalid UTF-8 or lone Unicode surrogates.
    """
    if not isinstance(connection_string, str):
        raise TypeError("A connection string must be a str")

    if any(unicodedata.category(character) in _FORBIDDEN_RAW_CATEGORIES for character in connection_string):
        raise MalformedConnectionStringError(
            "The connection string must not contain whitespace, control, format or unassigned characters"
        )

    scheme, separator, authority_and_suffix = connection_string.partition("://")
    if not separator or scheme.lower() != _SCHEME:
        raise UnsupportedSchemeError(f"The connection string scheme must be '{_SCHEME}://'")

    # Validate brackets before urlsplit, whose bracket checks vary between supported Python versions.
    authority = re.split(r"[/?#]", authority_and_suffix, maxsplit=1)[0]
    _validate_brackets(authority)

    # The sanitised error is raised outside the except block so that neither __cause__ nor __context__ keeps the
    # original exception, whose message and traceback frames can contain the credentials.
    try:
        parts = urlsplit(connection_string)
    except ValueError:
        parts = None
    if parts is None:
        raise MalformedConnectionStringError("The connection string is not a valid URL") from None

    user_info, has_user_info, host_and_port = parts.netloc.rpartition("@")
    host, port = _parse_host_and_port(host_and_port)

    if parts.path not in ("", "/"):
        raise UnsupportedOptionError("A path other than '/' is not supported")
    if parts.fragment or connection_string.endswith("#"):
        raise UnsupportedOptionError("A fragment is not supported")

    # Empty user info ("@host" or ":@host") carries no credentials, exactly like no user info in the .NET client.
    has_credentials = bool(has_user_info) and user_info not in ("", ":")
    client_id, client_secret = _parse_credentials(user_info, has_user_info=has_credentials)
    skip_tls_validation = _parse_query(parts.query, has_credentials=has_credentials)
    return ChronicleConnectionOptions(
        host=host,
        client_id=client_id,
        client_secret=client_secret,
        port=port,
        skip_tls_validation=skip_tls_validation,
    )


def _validate_brackets(authority: str) -> None:
    user_info, _, host_and_port = authority.rpartition("@")
    if "[" in user_info or "]" in user_info:
        raise InvalidHostError("Brackets are only supported around an IPv6 host")
    if "[" in host_and_port or "]" in host_and_port:
        if not host_and_port.startswith("[") or host_and_port.count("[") != 1 or host_and_port.count("]") != 1:
            raise InvalidHostError("An IPv6 host must be enclosed in one pair of brackets")
        _parse_host_and_port(host_and_port)


def _parse_host_and_port(host_and_port: str) -> tuple[str, int]:
    if host_and_port.startswith("["):
        closing = host_and_port.find("]")
        if closing == -1:
            raise InvalidHostError("An IPv6 address must be closed with ']'")
        # RFC 6874 encodes the zone delimiter as %25; also accept the raw delimiter without changing the zone id.
        host = host_and_port[1:closing].replace("%25", "%", 1)
        _, has_zone, zone = host.partition("%")
        if has_zone and not _ZONE_ID.fullmatch(zone):
            raise InvalidHostError("The IPv6 zone id must contain only letters, digits or '._~-'")
        remainder = host_and_port[closing + 1 :]
        if remainder and not remainder.startswith(":"):
            raise InvalidHostError("Unexpected text after the IPv6 address")
        port_text = remainder[1:] if remainder else None
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            invalid_ipv6 = True
        else:
            invalid_ipv6 = False
        if invalid_ipv6:
            # Do not retain an exception whose message can include the input host.
            raise InvalidHostError("The bracketed host is not a valid IPv6 address")
    else:
        if "," in host_and_port:
            raise InvalidHostError("Multiple hosts are not supported")
        if host_and_port.count(":") > 1:
            raise InvalidHostError("An IPv6 address must be enclosed in brackets")
        host, has_port, port_text_value = host_and_port.partition(":")
        port_text = port_text_value if has_port else None
        if not host:
            raise MissingHostError("The connection string does not name a host")
        host_name = host.removesuffix(".")
        if not host_name.isascii():
            host_name = _encode_idn_host(host_name)
        if len(host_name) > 253:
            raise InvalidHostError("The host name must not exceed 253 characters")
        labels = host_name.split(".")
        if any(not 1 <= len(label) <= 63 for label in labels):
            raise InvalidHostError("Host name labels must contain between 1 and 63 characters")
        if any(not _HOST_LABEL.fullmatch(label) for label in labels):
            raise InvalidHostError("The host contains characters that are not valid in a host name")

    return host, _parse_port(port_text)


def _encode_idn_host(host: str) -> str:
    """Validate Unicode DNS names through IDNA without changing the returned host representation."""
    ascii_labels = []
    for label in host.split("."):
        ascii_label: str | None
        try:
            ascii_label = label.lower().encode("idna").decode("ascii")
            round_trip_label = ascii_label.encode("ascii").decode("idna")
            if not label.isascii() and round_trip_label != unicodedata.normalize("NFC", label).lower():
                ascii_label = None
        except UnicodeError:
            ascii_label = None
        if ascii_label is None:
            # The codec exception can contain the input label; do not retain it in cause or context.
            raise InvalidHostError("The host is not a valid internationalised host name")
        ascii_labels.append(ascii_label)
    return ".".join(ascii_labels)


def _parse_port(port_text: str | None) -> int:
    if port_text is None:
        return DEFAULT_PORT
    if not _PORT.match(port_text):
        raise InvalidPortError("The port must be an integer between 1 and 65535")
    # Normalise before checking and converting: int() counts leading zeros towards the interpreter's digit limit.
    normalised_port = port_text.lstrip("0") or "0"
    if len(normalised_port) > 5:
        raise InvalidPortError("The port must be an integer between 1 and 65535")
    port = int(normalised_port)
    if not 1 <= port <= 65535:
        raise InvalidPortError("The port must be an integer between 1 and 65535")
    return port


def _parse_query(query: str, *, has_credentials: bool) -> bool:
    """Validate the query and return the value of ``skipTlsValidation``."""
    if not query:
        return True

    pairs = [(name.casefold(), value) for name, value in parse_qsl(query, keep_blank_values=True)]
    if not pairs:
        raise UnsupportedOptionError("An empty query string is not supported")

    # 'auth' is reported as unsupported before any ambiguity check, because in the .NET client
    # 'auth=none' wins over every other authentication option.
    if any(name == _AUTH for name, _ in pairs):
        raise UnsupportedOptionError("The 'auth' option is not supported yet")

    # An empty apiKey is absent, exactly like in the .NET client.
    if has_credentials and any(name == _API_KEY and value for name, value in pairs):
        raise AmbiguousAuthenticationError(
            "Client credentials cannot be combined with the 'apiKey' authentication option"
        )

    skip_tls_validation = True
    for name, value in pairs:
        if name == _SKIP_TLS_VALIDATION:
            if value.casefold() not in _BOOLEANS:
                raise UnsupportedOptionError("The 'skipTlsValidation' option must be 'true' or 'false'")
            skip_tls_validation = _BOOLEANS[value.casefold()]
        elif name == _API_KEY:
            if value:
                raise UnsupportedOptionError("The 'apiKey' authentication option is not supported yet")
        elif name == _AUTH:
            raise UnsupportedOptionError("The 'auth' option is not supported yet")
        else:
            raise UnsupportedOptionError("The query parameter is not supported yet")
    return skip_tls_validation


def _parse_credentials(user_info: str, *, has_user_info: bool) -> tuple[str, str]:
    if not has_user_info:
        return DEVELOPMENT_CLIENT_ID, DEVELOPMENT_CLIENT_SECRET

    raw_client_id, separator, raw_client_secret = user_info.partition(":")
    if not separator or not raw_client_id or not raw_client_secret:
        raise IncompleteCredentialsError("Both a client id and a client secret are required")
    if ":" in raw_client_secret:
        # The .NET client keeps only the text before a second ':', so an unencoded ':' would send a
        # different secret from each client. Require it to be percent-encoded instead.
        raise IncompleteCredentialsError("Encode ':' in the client secret as %3A")

    try:
        credentials = unquote(raw_client_id, errors="strict"), unquote(raw_client_secret, errors="strict")
    except UnicodeDecodeError:
        credentials = None

    if credentials is not None and not any(
        0xD800 <= ord(character) <= 0xDFFF for value in credentials for character in value
    ):
        return credentials

    # Raised outside the handler so neither __cause__ nor __context__ carries the decoder's message, which names the
    # offending byte of the credentials.
    raise InvalidCredentialsEncodingError("The credentials are not valid percent-encoded UTF-8")
