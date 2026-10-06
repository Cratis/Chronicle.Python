# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

import dataclasses
import traceback
from urllib.parse import quote

import pytest

from cratis_chronicle import (
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
from cratis_chronicle.connection_string import _parse_host_and_port


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


def test_exports_the_development_credentials() -> None:
    assert (DEVELOPMENT_CLIENT_ID, DEVELOPMENT_CLIENT_SECRET) == ("chronicle-dev-client", "chronicle-dev-secret")


@pytest.mark.parametrize("suffix", ["", "/", "/?apiKey=", "?apiKey=", "/?skipTlsValidation=true"])
def test_a_connection_string_without_credentials_equals_the_one_with_the_development_credentials(suffix: str) -> None:
    without_credentials = parse_connection_string(f"chronicle://localhost:35000{suffix}")
    with_credentials = parse_connection_string(
        f"chronicle://{DEVELOPMENT_CLIENT_ID}:{DEVELOPMENT_CLIENT_SECRET}@localhost:35000{suffix}"
    )

    assert without_credentials == with_credentials
    assert (without_credentials.client_id, without_credentials.client_secret) == (
        "chronicle-dev-client",
        "chronicle-dev-secret",
    )


def test_a_connection_string_without_credentials_and_a_port_uses_the_default_port() -> None:
    options = parse_connection_string("chronicle://localhost")

    assert (options.host, options.port) == ("localhost", DEFAULT_PORT)


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
        ("chronicle://id:se%3Acret@localhost", "id", "se:cret"),
        ("chronicle://i%5Bd%5D:se%5Bcret%5D@localhost", "i[d]", "se[cret]"),
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

    assert repr(options) == (
        "ChronicleConnectionOptions(host='localhost', client_id='id', port=35001, tls=True, skip_tls_validation=True)"
    )


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
    with pytest.raises(InvalidHostError):
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
        "chronicle://id@localhost",
        "chronicle://id:@localhost",
        "chronicle://:secret@localhost",
        "chronicle://id:se:cret@localhost",
    ],
)
def test_rejects_incomplete_credentials(connection_string: str) -> None:
    with pytest.raises(IncompleteCredentialsError):
        parse_connection_string(connection_string)


@pytest.mark.parametrize("secret", ["%FF", "%C3", "%80abc"])
def test_rejects_credentials_that_are_not_valid_utf8(secret: str) -> None:
    with pytest.raises(InvalidCredentialsEncodingError):
        parse_connection_string(f"chronicle://id:{secret}@localhost")


def test_rejects_credentials_partial_with_an_api_key() -> None:
    with pytest.raises(IncompleteCredentialsError):
        parse_connection_string("chronicle://id@localhost?apiKey=abc")


@pytest.mark.parametrize("query", ["apiKey=abc", "apikey=abc", "APIKEY=abc", "skipTlsValidation=false&apiKey=abc"])
def test_rejects_credentials_combined_with_an_api_key(query: str) -> None:
    with pytest.raises(AmbiguousAuthenticationError):
        parse_connection_string(f"chronicle://id:secret@localhost:35000/?{query}")


def test_rejects_credentials_combined_with_an_api_key_without_a_slash() -> None:
    with pytest.raises(AmbiguousAuthenticationError):
        parse_connection_string("chronicle://id:secret@localhost?apiKey=abc")


@pytest.mark.parametrize("query", ["apiKey=", "apiKey", "apikey="])
def test_treats_an_empty_api_key_as_absent(query: str) -> None:
    with_credentials = parse_connection_string(f"chronicle://id:secret@localhost/?{query}")
    without_credentials = parse_connection_string(f"chronicle://localhost/?{query}")

    assert with_credentials == parse_connection_string("chronicle://id:secret@localhost")
    assert without_credentials == parse_connection_string("chronicle://localhost")


@pytest.mark.parametrize("prefix", ["chronicle://localhost:35000", "chronicle://id:secret@localhost:35000"])
@pytest.mark.parametrize("query", ["auth=none", "auth=NONE", "auth=apiKey", "auth=", "auth"])
def test_reports_the_auth_option_as_unsupported(prefix: str, query: str) -> None:
    with pytest.raises(UnsupportedOptionError):
        parse_connection_string(f"{prefix}/?{query}")


def test_does_not_support_an_api_key_without_credentials_yet() -> None:
    with pytest.raises(UnsupportedOptionError):
        parse_connection_string("chronicle://localhost:35000?apiKey=abc")


def test_skips_tls_validation_by_default_while_tls_stays_on() -> None:
    options = parse_connection_string("chronicle://id:secret@localhost:35000")

    assert (options.tls, options.skip_tls_validation) == (True, True)


@pytest.mark.parametrize(("value", "expected"), [("true", True), ("false", False), ("TRUE", True), ("False", False)])
@pytest.mark.parametrize("prefix", ["chronicle://localhost:35000", "chronicle://id:secret@localhost:35000"])
def test_parses_skip_tls_validation(prefix: str, value: str, expected: bool) -> None:
    options = parse_connection_string(f"{prefix}/?skipTlsValidation={value}")

    assert (options.tls, options.skip_tls_validation) == (True, expected)


def test_parses_skip_tls_validation_case_insensitively_and_without_a_slash() -> None:
    assert parse_connection_string("chronicle://localhost?SKIPTLSVALIDATION=false").skip_tls_validation is False


def test_the_last_skip_tls_validation_wins() -> None:
    options = parse_connection_string("chronicle://localhost?skipTlsValidation=false&skipTlsValidation=true")

    assert options.skip_tls_validation is True


@pytest.mark.parametrize("value", ["", "1", "0", "yes", "no", "tru", "true%20"])
def test_rejects_a_skip_tls_validation_that_is_not_a_bool(value: str) -> None:
    with pytest.raises(UnsupportedOptionError):
        parse_connection_string(f"chronicle://localhost?skipTlsValidation={value}")


def test_rejects_skip_tls_validation_without_a_value() -> None:
    with pytest.raises(UnsupportedOptionError):
        parse_connection_string("chronicle://localhost?skipTlsValidation")


def test_combines_skip_tls_validation_with_an_empty_api_key() -> None:
    options = parse_connection_string("chronicle://id:secret@localhost?apiKey=&skipTlsValidation=false")

    assert options.skip_tls_validation is False


def test_str_shows_when_certificate_validation_is_required() -> None:
    options = parse_connection_string("chronicle://id:secret@localhost:35000?skipTlsValidation=false")

    assert str(options) == "chronicle://id:****@localhost:35000/?skipTlsValidation=false"
    assert parse_connection_string(str(options).replace("****", "secret")) == options


@pytest.mark.parametrize(
    "suffix",
    [
        "?loadBalancer=round-robin",
        "?srvNameServer=10.0.0.53",
        "?skipCompatibilityCheck=true",
        "?certificatePath=/tmp/cert.pfx",
        "?unknown",
        "?&",
        "/?unknown=1",
        "/?skipTlsValidation=false&unknown=1",
        "/events",
        "/#fragment",
        "#",
    ],
)
def test_rejects_options_that_are_not_supported_yet(suffix: str) -> None:
    with pytest.raises(UnsupportedOptionError):
        parse_connection_string(f"chronicle://id:secret@localhost:35000{suffix}")


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


def test_the_type_error_does_not_expose_an_input_derived_type_name() -> None:
    secret = "super-secret"
    value = type(secret, (), {})()
    with pytest.raises(TypeError) as caught:
        parse_connection_string(value)

    assert str(caught.value) == "A connection string must be a str"
    assert secret not in repr(caught.value)
    assert secret not in "".join(traceback.format_exception(caught.value))


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
        "chronicle://id:super-secret-value@localhost?skipTlsValidation=maybe",
        "chronicle://id:super-secret-value@local host",
        "chronicle://id:super%FFsecret-value@localhost",
        "http://id:super-secret-value@localhost",
        "chronicle://id:super-secret-value@local!host",
        "chronicle://id:super-secret-value@[not-an-address]",
        "chronicle://id:super-secret-value@localhost/super-secret-value",
        "chronicle://id:super-secret-value@localhost#super-secret-value",
        "chronicle://id:super-secret-value@localhost?auth=super-secret-value",
        "chronicle://localhost?apiKey=super-secret-value",
        "chronicle://:super-secret-value@localhost",
        "chronicle://id:super-secret-value:extra@localhost",
    ],
)
def test_error_messages_never_expose_the_secret(connection_string: str) -> None:
    with pytest.raises(ConnectionStringError) as caught:
        parse_connection_string(connection_string)

    for rendering in (str(caught.value), repr(caught.value), "".join(traceback.format_exception(caught.value))):
        assert "super" not in rendering
        assert "secret-value" not in rendering
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize("connection_string", ["chronicle://@localhost:35000", "chronicle://:@localhost:35000"])
def test_treats_empty_user_info_as_no_credentials(connection_string: str) -> None:
    assert parse_connection_string(connection_string) == parse_connection_string("chronicle://localhost:35000")


def test_reports_auth_as_unsupported_before_checking_for_ambiguity() -> None:
    with pytest.raises(UnsupportedOptionError):
        parse_connection_string("chronicle://id:secret@localhost?auth=none&apiKey=abc")


def test_invalid_credential_encoding_error_carries_no_decoder_cause_or_context() -> None:
    with pytest.raises(InvalidCredentialsEncodingError) as caught:
        parse_connection_string("chronicle://id:super%FFsecret@localhost")

    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_a_malformed_url_error_does_not_leak_the_credentials() -> None:
    secret = "super-secret"
    with pytest.raises(MalformedConnectionStringError) as caught:
        parse_connection_string(f"chronicle://id:{secret}@host\uff0fbad")

    formatted = "".join(traceback.format_exception(caught.value))
    assert secret not in formatted
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize("host", ["kernel.example.com.", "localhost.", "a."])
def test_accepts_an_absolute_host_name_with_a_trailing_dot(host: str) -> None:
    assert parse_connection_string(f"chronicle://id:secret@{host}:1234").host == host


@pytest.mark.parametrize("host", [".", "a..", ".a", "a.-"])
def test_rejects_a_malformed_trailing_dot_host(host: str) -> None:
    with pytest.raises(InvalidHostError):
        parse_connection_string(f"chronicle://id:secret@{host}")


@pytest.mark.parametrize("port", ["9" * 4400, "1" * 6, "0" * 4400 + "1" + "0" * 5])
def test_reports_an_over_long_port_as_an_invalid_port(port: str) -> None:
    with pytest.raises(InvalidPortError):
        parse_connection_string(f"chronicle://id:secret@localhost:{port}")


@pytest.mark.parametrize("port", ["00080", "0" * 4400 + "80"])
def test_accepts_a_port_with_leading_zeros(port: str) -> None:
    assert parse_connection_string(f"chronicle://id:secret@localhost:{port}").port == 80


def test_reports_a_port_of_thousands_of_zeros_as_an_invalid_port() -> None:
    port = "0" * 4400
    with pytest.raises(InvalidPortError) as caught:
        parse_connection_string(f"chronicle://id:secret@localhost:{port}")

    assert str(caught.value) == "The port must be an integer between 1 and 65535"


@pytest.mark.parametrize("query_name", ["super-secret@localhost", "super%2Dsecret%40localhost"])
def test_an_unsupported_query_error_does_not_expose_the_query_name(query_name: str) -> None:
    secret = "super-secret"
    with pytest.raises(UnsupportedOptionError) as caught:
        parse_connection_string(f"chronicle://id:35000?{query_name}")

    assert str(caught.value) == "The query parameter is not supported yet"
    for rendering in (str(caught.value), repr(caught.value), "".join(traceback.format_exception(caught.value))):
        assert secret not in rendering
        assert query_name not in rendering
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize("field", ["client_id", "client_secret"])
@pytest.mark.parametrize("surrogate", ["\ud800", "\udfff", "%ED%A0%80", "%ED%BF%BF"])
@pytest.mark.parametrize("percent_escape", ["", "%50"])
def test_rejects_surrogate_credentials_without_exposing_user_info(
    field: str, surrogate: str, percent_escape: str
) -> None:
    client_id = "PRIVATE_CLIENT"
    client_secret = "PRIVATE_SECRET"
    if field == "client_id":
        client_id += percent_escape + surrogate
    else:
        client_secret += percent_escape + surrogate
    connection_string = f"chronicle://{client_id}:{client_secret}@localhost"
    with pytest.raises(InvalidCredentialsEncodingError) as caught:
        parse_connection_string(connection_string)

    assert str(caught.value) == "The credentials are not valid percent-encoded UTF-8"
    for rendering in (str(caught.value), repr(caught.value), "".join(traceback.format_exception(caught.value))):
        assert "PRIVATE_CLIENT" not in rendering
        assert "PRIVATE_SECRET" not in rendering
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize("character", ["\u0080", "\u0085", "\u00a0", "\u2003", "\u2028", "\u200e", "\u2029"])
@pytest.mark.parametrize("field", ["client_id", "client_secret"])
def test_rejects_raw_unicode_whitespace_control_and_format_characters(character: str, field: str) -> None:
    client_id = "id" + (character if field == "client_id" else "")
    client_secret = "secret" + (character if field == "client_secret" else "")
    connection_string = f"chronicle://{client_id}:{client_secret}@localhost"
    with pytest.raises(MalformedConnectionStringError) as caught:
        parse_connection_string(connection_string)

    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize("character", ["\u0080", "\u0085", "\u00a0", "\u2003", "\u2028", "\u200e", "\u2029"])
@pytest.mark.parametrize("field", ["client_id", "client_secret"])
def test_preserves_percent_encoded_unicode_whitespace_control_and_format_characters(character: str, field: str) -> None:
    client_id = "id" + (quote(character) if field == "client_id" else "")
    client_secret = "secret" + (quote(character) if field == "client_secret" else "")
    options = parse_connection_string(f"chronicle://{client_id}:{client_secret}@localhost")

    assert options.client_id == "id" + (character if field == "client_id" else "")
    assert options.client_secret == "secret" + (character if field == "client_secret" else "")
    assert str(options)


@pytest.mark.parametrize(
    "authority",
    [
        "id:secret@[not-an-address]",
        "id:secret@[]",
        "id:secret@[::1",
        "id:secret@::1]",
        "id:secret@[[::1]]",
        "id:secret@[::1]]",
        "id:secret@[::1]x",
        "id:secret@x[::1]",
        "id:secret@[::1]:80]",
        "id:se[cret@localhost",
        "id:se]cret@localhost",
        "i[d:secret@localhost",
        "id:secret@[127.0.0.1]",
        "id:secret@[::1%]",
        "id:secret@[::1%25]",
    ],
)
def test_invalid_brackets_raise_a_host_error_before_urlsplit(authority: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_urlsplit(value: str) -> None:
        pytest.fail("Invalid brackets must be rejected before calling urlsplit")

    monkeypatch.setattr("cratis_chronicle.connection_string.urlsplit", unexpected_urlsplit)
    connection_string = f"chronicle://{authority}"
    with pytest.raises(InvalidHostError) as caught:
        parse_connection_string(connection_string)

    assert "secret" not in str(caught.value)
    assert "secret" not in repr(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    "host",
    [
        "a..b",
        "a.-b",
        "a-.b",
        "a" * 64,
        "a" * 64 + ".",
        ".".join(["a" * 63] * 4),
        ".".join(["a" * 63] * 3 + ["a" * 62]),
        ".".join(["a" * 63] * 3 + ["a" * 62]) + ".",
    ],
)
def test_rejects_invalid_dns_label_and_total_lengths(host: str) -> None:
    with pytest.raises(InvalidHostError):
        parse_connection_string(f"chronicle://id:secret@{host}")


@pytest.mark.parametrize(
    "host",
    ["a", "a" * 63, ".".join(["a" * 63] * 3 + ["a" * 61])],
)
@pytest.mark.parametrize("trailing_dot", ["", "."])
def test_accepts_dns_label_and_total_length_limits(host: str, trailing_dot: str) -> None:
    host += trailing_dot
    assert parse_connection_string(f"chronicle://id:secret@{host}").host == host


@pytest.mark.parametrize("host", ["fe80::1%eth0", "fe80::1%25eth0"])
def test_normalises_an_ipv6_zone_delimiter(host: str) -> None:
    options = parse_connection_string(f"chronicle://id:secret@[{host}]:35001")

    assert options.host == "fe80::1%eth0"
    assert str(options) == "chronicle://id:****@[fe80::1%eth0]:35001"
    assert parse_connection_string(str(options).replace("****", "secret")) == options


@pytest.mark.parametrize("zone", ["\ud800", "\udfff", "x:y", "é", "x$y", "x;y", "x%y", ""])
@pytest.mark.parametrize("delimiter", ["%", "%25"])
def test_rejects_an_invalid_ipv6_zone_with_a_fixed_chain_free_host_error(zone: str, delimiter: str) -> None:
    connection_string = f"chronicle://PRIVATE_CLIENT:PRIVATE_SECRET@[fe80::1{delimiter}{zone}]"
    with pytest.raises(InvalidHostError) as caught:
        parse_connection_string(connection_string)

    assert str(caught.value) == "The IPv6 zone id must contain only letters, digits or '._~-'"
    for rendering in (str(caught.value), repr(caught.value), "".join(traceback.format_exception(caught.value))):
        assert "PRIVATE_CLIENT" not in rendering
        assert "PRIVATE_SECRET" not in rendering
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize("zone", ["eth0", "1", "a._~-Z09"])
@pytest.mark.parametrize("delimiter", ["%", "%25"])
def test_accepts_rfc6874_zone_characters(zone: str, delimiter: str) -> None:
    options = parse_connection_string(f"chronicle://id:secret@[fe80::1{delimiter}{zone}]")

    assert options.host == f"fe80::1%{zone}"


def test_an_invalid_ipv6_host_error_does_not_retain_the_input_in_its_chain() -> None:
    secret = "super-secret"
    with pytest.raises(InvalidHostError) as caught:
        _parse_host_and_port(f"[{secret}]")

    assert str(caught.value) == "The bracketed host is not a valid IPv6 address"
    assert secret not in repr(caught.value)
    assert secret not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
