# Connection strings

`cratis_chronicle.parse_connection_string` turns a `chronicle://` connection string into immutable, typed options.
Parsing only describes the endpoint and the authentication mode. It does not open a channel or fetch a token.

```python
from cratis_chronicle import parse_connection_string

options = parse_connection_string("chronicle://my-client:my%40secret@localhost:35000")

options.host  # "localhost"
options.port  # 35000
options.client_id  # "my-client"
options.tls  # True
options.skip_tls_validation  # True
```

`ChronicleConnectionOptions.parse(...)` is the same call. The result is a frozen dataclass.

## Accepted shape

```text
chronicle://[<client-id>:<client-secret>@]<host>[:<port>][/][?skipTlsValidation=<true|false>]
```

- The port defaults to `35000`.
- The client id and client secret are percent-decoded. Encode reserved characters such as `@`, `:`, `/`, `?`, `#` and
  `%` in them.
- An IPv6 host must be enclosed in brackets, for example `chronicle://id:secret@[::1]:35000`.
- Direct kernel connections default to TLS (`options.tls` is `True`).
- Option names are case-insensitive.

## Development credentials

A connection string without credentials uses the development credentials, exactly like Chronicle's .NET client.
`chronicle://localhost:35000` and `chronicle://chronicle-dev-client:chronicle-dev-secret@localhost:35000` parse to equal
options. The values are exported as `DEVELOPMENT_CLIENT_ID` and `DEVELOPMENT_CLIENT_SECRET`. They are well-known
development values and only work against a kernel explicitly configured to accept them.

A partial set of credentials is an error: `id@host`, `id:@host` and `:secret@host` raise `IncompleteCredentialsError`.
Empty user info (`@host` or `:@host`) carries no credentials and uses the development defaults, as in the .NET client.
Percent-encode a `:` in the client secret as `%3A`; an unencoded one raises `IncompleteCredentialsError`, because the
.NET client would keep only the text before it.

## TLS certificate validation

`skipTlsValidation` is a boolean that defaults to `true`, as in the .NET client: the connection always uses TLS, but the
kernel certificate is accepted without validation so a development kernel with a self-signed certificate works.
Pass `skipTlsValidation=false` to require a verifiable certificate. `true` and `false` are accepted; any other value
raises `UnsupportedOptionError`. The result is `options.skip_tls_validation`; `options.tls` stays `True` either way.

```python
parse_connection_string("chronicle://localhost:35000/?skipTlsValidation=false").skip_tls_validation  # False
```

## Redaction

`str()` and `repr()` of the options never contain the client secret. `str()` renders
`chronicle://my-client:****@localhost:35000`.

## Rejected input

Every rejection is a subclass of `ConnectionStringError` (itself a `ValueError`).

| Input | Error |
| --- | --- |
| A scheme other than `chronicle://`, including `chronicle+srv://` | `UnsupportedSchemeError` |
| No host | `MissingHostError` |
| An invalid host, or more than one host | `InvalidHostError` |
| A port that is not an integer from 1 to 65535 | `InvalidPortError` |
| Only one of the client id and client secret, or an empty one | `IncompleteCredentialsError` |
| Credentials that are not valid percent-encoded UTF-8 | `InvalidCredentialsEncodingError` |
| Client credentials combined with a non-empty `apiKey` | `AmbiguousAuthenticationError` |
| A non-empty `apiKey` without credentials, any `auth=...`, a `skipTlsValidation` that is not `true` or `false`, any other query parameter, a path other than `/`, or a fragment | `UnsupportedOptionError` |
| Whitespace or control characters | `MalformedConnectionStringError` |

An empty `apiKey` is treated as absent. API key authentication (`apiKey=<key>` without credentials), `auth=none` and
multiple hosts are not supported yet. They are rejected rather than ignored, so a connection never silently behaves
differently from what the string asks for.
