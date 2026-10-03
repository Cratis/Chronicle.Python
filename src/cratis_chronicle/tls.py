# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

"""Decides which certificates the client trusts. Production connections always verify the certificate and host name."""

from __future__ import annotations

import asyncio
import ipaddress
import ssl
from collections.abc import Callable
from dataclasses import dataclass

from .connection_string import ChronicleConnectionOptions

__all__ = ["TlsTrust", "is_loopback_host", "resolve_tls_trust"]

CertificateFetcher = Callable[[str, int], str]


@dataclass(frozen=True, slots=True)
class TlsTrust:
    """The trusted root certificates, as PEM, or ``None`` to use the platform's default roots.

    Certificate and host name verification stay on in both cases.
    """

    root_certificates: bytes | None

    def ssl_context(self) -> ssl.SSLContext:
        """Create a verifying SSL context that trusts exactly these roots (or the platform defaults)."""
        if self.root_certificates is None:
            return ssl.create_default_context()
        context = ssl.create_default_context(cadata=self.root_certificates.decode("ascii"))
        # A development certificate is self-signed and typically lacks the extensions strict mode demands. Trust is
        # still limited to this one certificate and the host name is still checked.
        context.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
        return context


def is_loopback_host(host: str) -> bool:
    """Return whether ``host`` is ``localhost`` or a loopback IP address."""
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


async def resolve_tls_trust(
    options: ChronicleConnectionOptions,
    *,
    ca_certificates: bytes | None = None,
    fetch_certificate: CertificateFetcher | None = None,
) -> TlsTrust | None:
    """Resolve the trust for a connection, or ``None`` when the connection does not use TLS.

    Explicit ``ca_certificates`` always win. Otherwise the certificates are verified against the platform roots,
    with one development exception: when ``skip_tls_validation`` is set (the connection string default) *and* the host
    is a loopback address, the certificate the local kernel presents is trusted. The host name is still verified. For
    any other host the option is ignored and the certificate must chain to a trusted root, so a remote kernel can
    never be reached with relaxed validation.
    """
    if not options.tls:
        return None
    if ca_certificates is not None:
        return TlsTrust(ca_certificates)
    if options.skip_tls_validation and is_loopback_host(options.host):
        fetch = fetch_certificate or _fetch_certificate
        pem = await asyncio.to_thread(fetch, options.host, options.port)
        return TlsTrust(pem.encode("ascii"))
    return TlsTrust(None)


def _fetch_certificate(host: str, port: int) -> str:
    return ssl.get_server_certificate((host, port), timeout=10)
