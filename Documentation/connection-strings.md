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
```

`ChronicleConnectionOptions.parse(...)` is the same call. The result is a frozen dataclass.

## Accepted shape

```text
chronicle://<client-id>:<client-secret>@<host>[:<port>][/]
```

- The port defaults to `35000`.
- The client id and client secret are percent-decoded. Encode reserved characters such as `@`, `:`, `/`, `?`, `#` and
  `%` in them.
- An IPv6 host must be enclosed in brackets, for example `chronicle://id:secret@[::1]:35000`.
- Direct kernel connections default to TLS (`options.tls` is `True`).

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
| A missing or empty client id or client secret | `IncompleteCredentialsError` |
| Credentials that are not valid percent-encoded UTF-8 | `InvalidCredentialsEncodingError` |
| Client credentials combined with `apiKey` or `auth` | `AmbiguousAuthenticationError` |
| Any other query parameter, a path other than `/`, or a fragment | `UnsupportedOptionError` |
| Whitespace or control characters | `MalformedConnectionStringError` |

Query parameters such as `skipTlsValidation`, `apiKey` and `auth=none`, and multiple hosts, are not supported yet.
They are rejected rather than ignored, so a connection never silently behaves differently from what the string asks
for.
