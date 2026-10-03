# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

"""Experimental Python client for Cratis Chronicle."""

from importlib.metadata import PackageNotFoundError, version

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

try:
    __version__ = version("cratis-chronicle")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
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
