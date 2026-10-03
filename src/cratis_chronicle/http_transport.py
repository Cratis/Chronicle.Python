# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

"""A minimal asyncio HTTP/1.1 form-POST transport for the OAuth token endpoint.

It exists so a request can be cancelled for real and so the client needs no HTTP dependency. It follows no redirects,
which keeps the client secret from ever being sent to a host the caller did not configure.
"""

from __future__ import annotations

import asyncio
import ssl
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode, urlsplit

from .errors import TokenRequestError

__all__ = ["HttpResponse", "StreamFormTransport", "TokenTransport"]

_MAX_RESPONSE_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """The status and body of an HTTP response."""

    status: int
    body: bytes


class TokenTransport(Protocol):
    """Sends the token request. Replaceable so the provider can be tested without a network."""

    async def post_form(self, url: str, fields: Mapping[str, str]) -> HttpResponse:
        """POST ``fields`` as ``application/x-www-form-urlencoded`` to ``url`` and return the response."""
        ...


class StreamFormTransport:
    """Sends the request over a fresh asyncio connection that is closed after the response."""

    def __init__(self, ssl_context: ssl.SSLContext | None, *, timeout: float = 30.0) -> None:
        self._ssl_context = ssl_context
        self._timeout = timeout

    async def post_form(self, url: str, fields: Mapping[str, str]) -> HttpResponse:
        parts = urlsplit(url)
        secure = parts.scheme == "https"
        host = parts.hostname or ""
        port = parts.port or (443 if secure else 80)
        body = urlencode(fields).encode("ascii")
        host_header = parts.netloc.rpartition("@")[2]
        head = (
            f"POST {parts.path or '/'} HTTP/1.1\r\nHost: {host_header}\r\n"
            "Content-Type: application/x-www-form-urlencoded\r\nAccept: application/json\r\n"
            f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
        ).encode("ascii")
        try:
            return await asyncio.wait_for(self._exchange(host, port, secure, head + body), self._timeout)
        except (TimeoutError, asyncio.TimeoutError) as error:
            raise TokenRequestError("The token request timed out") from error
        except ssl.SSLError as error:
            raise TokenRequestError(
                f"The TLS handshake with the token endpoint failed: {error.reason or 'ssl error'}"
            ) from error
        except (OSError, EOFError, ValueError) as error:
            raise TokenRequestError(f"The token endpoint could not be reached ({type(error).__name__})") from error

    async def _exchange(self, host: str, port: int, secure: bool, payload: bytes) -> HttpResponse:
        reader, writer = await asyncio.open_connection(
            host,
            port,
            ssl=(self._ssl_context or ssl.create_default_context()) if secure else None,
            server_hostname=host if secure else None,
        )
        try:
            writer.write(payload)
            await writer.drain()
            return _parse_response(await _read_to_end(reader))
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, ssl.SSLError):
                pass


async def _read_to_end(reader: asyncio.StreamReader) -> bytes:
    """Read until the server closes the connection (the request said ``Connection: close``), within the size bound."""
    raw = bytearray()
    while chunk := await reader.read(65536):
        raw += chunk
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise ValueError("response too large")
    return bytes(raw)


def _parse_response(raw: bytes) -> HttpResponse:
    head, separator, body = raw.partition(b"\r\n\r\n")
    if not separator:
        raise ValueError("incomplete response")
    lines = head.decode("latin-1").split("\r\n")
    status_parts = lines[0].split(" ", 2)
    if len(status_parts) < 2 or not status_parts[1].isdigit():
        raise ValueError("invalid status line")
    headers = {}
    for line in lines[1:]:
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip().lower()
    if "chunked" in headers.get("transfer-encoding", ""):
        body = _decode_chunked(body)
    elif "content-length" in headers:
        length = headers["content-length"]
        if not length.isascii() or not length.isdigit():
            raise ValueError("invalid content length")
        if len(body) < int(length):
            raise ValueError("truncated body")
        body = body[: int(length)]
    return HttpResponse(status=int(status_parts[1]), body=body)


def _decode_chunked(data: bytes) -> bytes:
    decoded = bytearray()
    while True:
        size_line, separator, data = data.partition(b"\r\n")
        if not separator:
            raise ValueError("invalid chunked body")
        size = int(size_line.split(b";", 1)[0], 16)
        if size == 0:
            return bytes(decoded)
        if len(data) < size + 2:
            raise ValueError("truncated chunked body")
        decoded += data[:size]
        data = data[size + 2 :]
