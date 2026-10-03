# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

import asyncio
import shutil
import ssl
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from cratis_chronicle import StreamFormTransport, TlsTrust, TokenRequestError
from cratis_chronicle.http_transport import _decode_chunked, _parse_response

Handler = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]


async def serve(handler: Handler, context: ssl.SSLContext | None = None) -> tuple[asyncio.Server, int]:
    server = await asyncio.start_server(handler, "127.0.0.1", 0, ssl=context)
    return server, server.sockets[0].getsockname()[1]


async def read_request(reader: asyncio.StreamReader) -> tuple[str, bytes]:
    head = await reader.readuntil(b"\r\n\r\n")
    length = next(
        int(line.split(b":")[1]) for line in head.split(b"\r\n") if line.lower().startswith(b"content-length")
    )
    return head.decode(), await reader.readexactly(length)


def test_posts_a_form_and_reads_a_content_length_response() -> None:
    seen: list[tuple[str, bytes]] = []

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        seen.append(await read_request(reader))
        writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 7\r\n\r\n{"a":1}')
        await writer.drain()
        writer.close()

    async def scenario() -> tuple[int, bytes]:
        server, port = await serve(handler)
        async with server:
            response = await StreamFormTransport(None).post_form(
                f"http://127.0.0.1:{port}/connect/token", {"client_secret": "a b&c", "grant_type": "x"}
            )
        return response.status, response.body

    assert asyncio.run(scenario()) == (200, b'{"a":1}')
    head, body = seen[0]
    assert head.startswith("POST /connect/token HTTP/1.1")
    assert "content-type: application/x-www-form-urlencoded" in head.lower()
    assert body == b"client_secret=a+b%26c&grant_type=x"


def test_reads_a_chunked_response() -> None:
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await read_request(reader)
        writer.write(b"HTTP/1.1 401 Unauthorized\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n2\r\nde\r\n0\r\n\r\n")
        await writer.drain()
        writer.close()

    async def scenario() -> tuple[int, bytes]:
        server, port = await serve(handler)
        async with server:
            response = await StreamFormTransport(None).post_form(f"http://127.0.0.1:{port}/x", {})
        return response.status, response.body

    assert asyncio.run(scenario()) == (401, b"abcde")


def test_a_redirect_is_returned_not_followed() -> None:
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await read_request(reader)
        writer.write(b"HTTP/1.1 302 Found\r\nLocation: http://elsewhere.invalid/\r\nContent-Length: 0\r\n\r\n")
        await writer.drain()
        writer.close()

    async def scenario() -> int:
        server, port = await serve(handler)
        async with server:
            return (await StreamFormTransport(None).post_form(f"http://127.0.0.1:{port}/x", {})).status

    assert asyncio.run(scenario()) == 302


def test_a_timeout_is_a_request_error() -> None:
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await read_request(reader)
        await asyncio.sleep(1)
        writer.close()

    async def scenario() -> None:
        server, port = await serve(handler)
        async with server:
            await StreamFormTransport(None, timeout=0.2).post_form(f"http://127.0.0.1:{port}/x", {})

    with pytest.raises(TokenRequestError, match="timed out"):
        asyncio.run(scenario())


def test_a_refused_connection_is_a_request_error_without_secrets() -> None:
    async def scenario() -> None:
        server, port = await serve(lambda r, w: asyncio.sleep(0))  # type: ignore[arg-type, return-value]
        server.close()
        await server.wait_closed()
        await StreamFormTransport(None).post_form(f"http://127.0.0.1:{port}/x", {"client_secret": "hunter2"})

    with pytest.raises(TokenRequestError) as raised:
        asyncio.run(scenario())

    assert "hunter2" not in str(raised.value)


def test_a_garbled_response_is_a_request_error() -> None:
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await read_request(reader)
        writer.write(b"garbage")
        await writer.drain()
        writer.close()

    async def scenario() -> None:
        server, port = await serve(handler)
        async with server:
            await StreamFormTransport(None).post_form(f"http://127.0.0.1:{port}/x", {})

    with pytest.raises(TokenRequestError):
        asyncio.run(scenario())


def test_chunk_and_status_parsers_reject_malformed_input() -> None:
    with pytest.raises(ValueError):
        _decode_chunked(b"zz\r\nabc")
    with pytest.raises(ValueError):
        _decode_chunked(b"5\r\nab")
    with pytest.raises(ValueError):
        _parse_response(b"HTTP/1.1 abc\r\n\r\n")


@pytest.fixture
def self_signed(tmp_path: Path) -> tuple[Path, Path]:
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.skip("openssl is not available")
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(  # noqa: S603
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost,IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )
    return cert, key


def tls_scenario(self_signed: tuple[Path, Path], transport: StreamFormTransport) -> int:
    cert, key = self_signed
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert, key)

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await read_request(reader)
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}")
        await writer.drain()
        writer.close()

    async def scenario() -> int:
        server, port = await serve(handler, server_context)
        async with server:
            return (await transport.post_form(f"https://localhost:{port}/x", {})).status

    return asyncio.run(scenario())


def test_an_untrusted_self_signed_certificate_is_rejected_by_default(self_signed: tuple[Path, Path]) -> None:
    transport = StreamFormTransport(TlsTrust(None).ssl_context())

    with pytest.raises(TokenRequestError, match="TLS handshake"):
        tls_scenario(self_signed, transport)


def test_explicitly_trusting_the_certificate_allows_the_connection(self_signed: tuple[Path, Path]) -> None:
    trust = TlsTrust(self_signed[0].read_bytes())

    assert tls_scenario(self_signed, StreamFormTransport(trust.ssl_context())) == 200


def test_trusting_one_certificate_still_verifies_the_host_name(self_signed: tuple[Path, Path]) -> None:
    cert, key = self_signed
    context = TlsTrust(cert.read_bytes()).ssl_context()
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert, key)

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.close()

    async def scenario() -> None:
        server, port = await serve(handler, server_context)
        async with server:
            # 127.0.0.1 is in the certificate, but a different name is not.
            await StreamFormTransport(context).post_form(f"https://localhost.localdomain:{port}/x", {})

    with pytest.raises(TokenRequestError):
        asyncio.run(scenario())
