# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

import asyncio

import pytest

from cratis_chronicle import ChronicleConnectionOptions, is_loopback_host, resolve_tls_trust


def options(host: str, **overrides: object) -> ChronicleConnectionOptions:
    return ChronicleConnectionOptions(host=host, client_id="id", client_secret="secret", **overrides)  # type: ignore[arg-type]


def resolve(opts: ChronicleConnectionOptions, ca: bytes | None = None) -> tuple[object, list[tuple[str, int]]]:
    fetched: list[tuple[str, int]] = []

    def fetch(host: str, port: int) -> str:
        fetched.append((host, port))
        return "-----BEGIN CERTIFICATE-----\nabc\n-----END CERTIFICATE-----\n"

    return asyncio.run(resolve_tls_trust(opts, ca_certificates=ca, fetch_certificate=fetch)), fetched


@pytest.mark.parametrize("host", ["localhost", "LOCALHOST", "127.0.0.1", "127.5.5.5", "::1"])
def test_loopback_hosts_are_recognized(host: str) -> None:
    assert is_loopback_host(host)


@pytest.mark.parametrize("host", ["kernel.example", "10.0.0.5", "localhost.example.com", "2001:db8::1"])
def test_other_hosts_are_not_loopback(host: str) -> None:
    assert not is_loopback_host(host)


def test_a_loopback_development_kernel_certificate_is_trusted_when_skip_validation_is_set() -> None:
    trust, fetched = resolve(options("localhost", port=19300))

    assert fetched == [("localhost", 19300)]
    assert trust.root_certificates is not None  # type: ignore[attr-defined]


def test_a_remote_host_never_gets_relaxed_validation_even_when_skip_validation_is_set() -> None:
    trust, fetched = resolve(options("kernel.example"))

    assert fetched == []
    assert trust.root_certificates is None  # type: ignore[attr-defined]


def test_loopback_verifies_normally_when_skip_validation_is_off() -> None:
    trust, fetched = resolve(options("localhost", skip_tls_validation=False))

    assert fetched == []
    assert trust.root_certificates is None  # type: ignore[attr-defined]


def test_explicit_ca_certificates_win_and_nothing_is_fetched() -> None:
    trust, fetched = resolve(options("localhost"), ca=b"PEM")

    assert fetched == []
    assert trust.root_certificates == b"PEM"  # type: ignore[attr-defined]


def test_no_trust_is_resolved_without_tls() -> None:
    trust, fetched = resolve(options("localhost", tls=False))

    assert trust is None
    assert fetched == []
