# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

import dataclasses

import pytest

from cratis_chronicle import (
    DEFAULT_PORT,
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


def test_parses_host_port_and_credentials() -> None:
    options = parse_connection_string("chronicle://chronicle-dev-client:chronicle-dev-secret@localhost:35100")

    assert options == ChronicleConnectionOptions(
        host="localhost", client_id="chronicle-dev-client", client_secret="chronicle-dev-secret", port=35100
    )


def test_defaults_the_port_to_35000() -> None:
    options = parse_connection_string("chronicle://id:secret@kernel.example.com")

    assert options.port == DEFAULT_PORT == 35000


def test_defaults_to_tls() -> None:
    assert parse_connection_string("chronicle://id:secret@localhost:35000").tls is True


def test_accepts_a_trailing_slash() -> None:
    assert parse_connection_string("chronicle://id:secret@localhost:35000/").host == "localhost"


def test_accepts_an_upper_case_scheme() -> None:
    assert parse_connection_string("CHRONICLE://id:secret@localhost").host == "localhost"


def test_parse_classmethod_matches_the_function() -> None:
    connection_string = "chronicle://id:secret@localhost:35000"

    assert ChronicleConnectionOptions.parse(connection_string) == parse_connection_string(connection_string)


def test_parses_a_bracketed_ipv6_host() -> None:
    options = parse_connection_string("chronicle://id:secret@[::1]:35001")

    assert (options.host, options.port) == ("::1", 35001)


def test_parses_a_bracketed_ipv6_host_with_the_default_port() -> None:
    options = parse_connection_string("chronicle://id:secret@[::1]")

    assert (options.host, options.port) == ("::1", DEFAULT_PORT)


def test_parses_an_ipv4_host() -> None:
    assert parse_connection_string("chronicle://id:secret@127.0.0.1:35000").host == "127.0.0.1"


@pytest.mark.parametrize(
    ("connection_string", "client_id", "client_secret"),
    [
        ("chronicle://my%40client:p%40ss%3Aw%2Ford%3F%23@localhost", "my@client", "p@ss:w/ord?#"),
        ("chronicle://id:a%25b@localhost", "id", "a%b"),
        ("chronicle://id:sp%20ace@localhost", "id", "sp ace"),
        ("chronicle://id:caf%C3%A9@localhost", "id", "café"),
        ("chronicle://id:a+b@localhost", "id", "a+b"),
        ("chronicle://id:se:cret@localhost", "id", "se:cret"),
    ],
)
def test_preserves_percent_encoded_credentials(connection_string: str, client_id: str, client_secret: str) -> None:
    options = parse_connection_string(connection_string)

    assert (options.client_id, options.client_secret) == (client_id, client_secret)


def test_options_are_immutable() -> None:
    options = parse_connection_string("chronicle://id:secret@localhost")

    with pytest.raises(dataclasses.FrozenInstanceError):
        options.host = "other"  # type: ignore[misc]


def test_options_can_be_hashed_and_compared() -> None:
    first = parse_connection_string("chronicle://id:secret@localhost")
    second = parse_connection_string("chronicle://id:secret@localhost:35000")

    assert first == second
    assert len({first, second}) == 1


@pytest.mark.parametrize(
    "rendering",
    [
        pytest.param(lambda options: repr(options), id="repr"),
        pytest.param(lambda options: str(options), id="str"),
        pytest.param(lambda options: f"{options}", id="format"),
        pytest.param(lambda options: f"{options!r}", id="format-repr"),
    ],
)
def test_renderings_never_expose_the_client_secret(rendering: object) -> None:
    options = parse_connection_string("chronicle://id:top%20secret%21@localhost:35000")

    for secret in ("top secret!", "top%20secret%21", "top", "secret"):
        assert secret not in rendering(options)  # type: ignore[operator]


def test_str_shows_the_redacted_endpoint() -> None:
    options = parse_connection_string("chronicle://my%40client:secret@[::1]:35001")

    assert str(options) == "chronicle://my%40client:****@[::1]:35001"


def test_repr_shows_the_non_secret_fields() -> None:
    options = parse_connection_string("chronicle://id:secret@localhost:35001")

    assert repr(options) == "ChronicleConnectionOptions(host='localhost', client_id='id', port=35001, tls=True)"


@pytest.mark.parametrize(
    "connection_string",
    [
        "http://id:secret@localhost",
        "https://id:secret@localhost",
        "chronicle+srv://id:secret@cluster.example.com",
        "chronicles://id:secret@localhost",
        "id:secret@localhost:35000",
        "localhost:35000",
        "//id:secret@localhost",
        "",
    ],
)
def test_rejects_an_unsupported_scheme(connection_string: str) -> None:
    with pytest.raises(UnsupportedSchemeError):
        parse_connection_string(connection_string)


@pytest.mark.parametrize(
    "connection_string",
    [
        "chronicle://",
        "chronicle://id:secret@",
        "chronicle://id:secret@:35000",
        "chronicle://:35000",
        "chronicle:///",
    ],
)
def test_rejects_a_missing_host(connection_string: str) -> None:
    with pytest.raises(MissingHostError):
        parse_connection_string(connection_string)


@pytest.mark.parametrize(
    "connection_string",
    [
        "chronicle://id:secret@node1:35000,node2:35000",
        "chronicle://id:secret@node1,node2",
        "chronicle://id:secret@::1",
        "chronicle://id:secret@[::1",
        "chronicle://id:secret@[not-an-address]",
        "chronicle://id:secret@[::1]x",
        "chronicle://id:secret@-bad-",
        "chronicle://id:secret@bad_host!",
        "chronicle://id:secret@ex%61mple.com",
    ],
)
def test_rejects_an_invalid_host(connection_string: str) -> None:
    with pytest.raises((InvalidHostError, MalformedConnectionStringError)):
        parse_connection_string(connection_string)


@pytest.mark.parametrize(
    "port", ["", "0", "65536", "-1", "abc", "35000x", "3 5", "1.5", "+80", "٣٥٠٠٠", "99999999999999999999"]
)
def test_rejects_an_invalid_port(port: str) -> None:
    with pytest.raises((InvalidPortError, MalformedConnectionStringError)):
        parse_connection_string(f"chronicle://id:secret@localhost:{port}")


@pytest.mark.parametrize("port", ["", "0", "65536", "abc", "-1", "+80"])
def test_reports_the_port_error_type(port: str) -> None:
    with pytest.raises(InvalidPortError):
        parse_connection_string(f"chronicle://id:secret@localhost:{port}")


@pytest.mark.parametrize("port", ["1", "65535"])
def test_accepts_the_port_range_limits(port: str) -> None:
    assert parse_connection_string(f"chronicle://id:secret@localhost:{port}").port == int(port)


@pytest.mark.parametrize(
    "connection_string",
    [
        "chronicle://localhost:35000",
        "chronicle://id@localhost",
        "chronicle://id:@localhost",
        "chronicle://:secret@localhost",
        "chronicle://:@localhost",
        "chronicle://@localhost",
    ],
)
def test_rejects_incomplete_credentials(connection_string: str) -> None:
    with pytest.raises(IncompleteCredentialsError):
        parse_connection_string(connection_string)


@pytest.mark.parametrize("secret", ["%FF", "%C3", "%80abc"])
def test_rejects_credentials_that_are_not_valid_utf8(secret: str) -> None:
    with pytest.raises(InvalidCredentialsEncodingError):
        parse_connection_string(f"chronicle://id:{secret}@localhost")


@pytest.mark.parametrize(
    "query",
    ["apiKey=abc", "apikey=abc", "auth=none", "auth=none&apiKey=abc", "skipTlsValidation=true&auth=none", "apiKey="],
)
def test_rejects_ambiguous_authentication(query: str) -> None:
    with pytest.raises(AmbiguousAuthenticationError):
        parse_connection_string(f"chronicle://id:secret@localhost:35000/?{query}")


def test_rejects_credentials_combined_with_an_authentication_option_without_a_slash() -> None:
    with pytest.raises(AmbiguousAuthenticationError):
        parse_connection_string("chronicle://id:secret@localhost?auth=none")


@pytest.mark.parametrize(
    "suffix",
    [
        "?skipTlsValidation=true",
        "?loadBalancer=round-robin",
        "?srvNameServer=10.0.0.53",
        "?skipCompatibilityCheck=true",
        "?unknown",
        "?&",
        "/?unknown=1",
        "/events",
        "/#fragment",
        "#",
    ],
)
def test_rejects_options_that_are_not_supported_yet(suffix: str) -> None:
    with pytest.raises(UnsupportedOptionError):
        parse_connection_string(f"chronicle://id:secret@localhost:35000{suffix}")


@pytest.mark.parametrize("suffix", ["?apiKey=abc", "?auth=none"])
def test_does_not_support_non_credential_authentication_yet(suffix: str) -> None:
    with pytest.raises(UnsupportedOptionError):
        parse_connection_string(f"chronicle://localhost:35000{suffix}")


@pytest.mark.parametrize(
    "connection_string",
    [
        "chronicle://id:secret@local host",
        "chronicle://id:sec ret@localhost",
        " chronicle://id:secret@localhost",
        "chronicle://id:secret@localhost\n",
    ],
)
def test_rejects_whitespace_and_control_characters(connection_string: str) -> None:
    with pytest.raises(MalformedConnectionStringError):
        parse_connection_string(connection_string)


def test_rejects_a_value_that_is_not_a_string() -> None:
    with pytest.raises(TypeError):
        parse_connection_string(None)  # type: ignore[arg-type]


def test_every_error_is_a_connection_string_error_and_a_value_error() -> None:
    with pytest.raises(ConnectionStringError) as caught:
        parse_connection_string("http://localhost")

    assert isinstance(caught.value, ValueError)


@pytest.mark.parametrize(
    "connection_string",
    [
        "chronicle://id:super-secret-value@",
        "chronicle://id:super-secret-value@localhost:0",
        "chronicle://id:super-secret-value@localhost?apiKey=abc",
        "chronicle://id:super-secret-value@local host",
        "chronicle://id:super%FFsecret-value@localhost",
    ],
)
def test_error_messages_never_expose_the_secret(connection_string: str) -> None:
    with pytest.raises(ConnectionStringError) as caught:
        parse_connection_string(connection_string)

    assert "super" not in str(caught.value)
    assert "secret-value" not in str(caught.value)
