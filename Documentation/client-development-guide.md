# Building the Chronicle Python client

This guide defines the starting sequence for a Python client. It keeps the first contribution small enough to
review and verify while preserving Chronicle's generated wire contract.

## Architecture boundary

Chronicle exposes gRPC services generated from code-first contracts in the core
[`Cratis/Chronicle`](https://github.com/Cratis/Chronicle) repository.

The core release pipeline owns a low-level Python package generated from those `.proto` files. This repository
owns the idiomatic client that consumes that package. Generated messages and stubs must not be copied, edited, or
recreated by hand here.

```text
Chronicle C# contracts
  -> generated .proto files
    -> generated Python contracts package
      -> idiomatic Chronicle.Python API
```

### Temporary contracts distribution

`cratis-chronicle-contracts` is not published to PyPI. The project dependency resolves the verified
`cratis-chronicle-contracts` 16.38.2 wheel from its matching
[Chronicle GitHub release](https://github.com/Cratis/Chronicle/releases/tag/v16.38.2), pinned by SHA-256 in
`pyproject.toml`. A normal development install fetches it automatically, so the install needs network access to
GitHub release assets. Do not copy generated contracts into this repository.

The PyPI trusted-publishing setup ([#15](https://github.com/Cratis/Chronicle.Python/issues/15)) and first
publication ([#16](https://github.com/Cratis/Chronicle.Python/issues/16)) were closed as not planned, so there is
no scheduled move to PyPI. The contracts wheel is generated from the v16.38.2 kernel; see
[Kernel version](#kernel-version) before testing against a newer kernel.

## Local kernel

The development kernel listens on port `35000`. Its single listener uses TLS and serves gRPC over HTTP/2, the OAuth
token endpoint, and the Workbench. The development image generates a self-signed certificate at startup and accepts
built-in development client credentials.

Start the development image that matches the contracts version, bound to the loopback interface only:

```shell
docker run --rm -p 127.0.0.1:35000:35000 cratis/chronicle:16.38.2-development
```

The development image embeds MongoDB inside the container, so every event disappears when the container stops.

Use the explicit local-development connection string:

```text
chronicle://chronicle-dev-client:chronicle-dev-secret@localhost:35000
```

These credentials are development defaults only. They are not production credentials or a production
configuration contract.

### Kernel version

The contracts and the probe below were exercised against `cratis/chronicle:16.38.2-development`. Newer kernels,
including `latest-development`, may add or change contracts; compatibility between the 16.38.2 contracts and a
later kernel has not been verified. Name the exact kernel image in any issue, test, or pull request that exercises
network behavior.

## Authentication contract

Request a token from:

```text
https://localhost:35000/connect/token
```

Send an `application/x-www-form-urlencoded` body with:

```text
grant_type=client_credentials
client_id=<client id>
client_secret=<client secret>
```

Parse `access_token` and `expires_in` (seconds) from the JSON response. Attach the current token to each new gRPC
call as metadata:

```text
authorization: Bearer <access token>
```

Token acquisition, caching, expiry, refresh, and call interception should remain separate from the channel. Do
not permanently bake one expiring token into channel headers. Chronicle's
[authentication and bearer tokens](https://www.cratis.io/chronicle/building-a-client/authentication-and-bearer-tokens/)
page describes the behavior the other clients implement: the three authentication modes selected by the connection
string, proactive refresh before expiry, and one retry after an `UNAUTHENTICATED` response.

### TLS and certificate validation

The development kernel's self-signed certificate names `localhost`, `chronicle`, `127.0.0.1`, and `::1`. A Python
gRPC channel rejects it unless the certificate is supplied as a trusted root. A development option may explicitly
relax certificate verification for localhost. Production behavior must retain normal certificate and hostname
validation.

Chronicle's .NET client differs: it accepts any server certificate unless validation is turned on; see
[TLS configuration](https://www.cratis.io/chronicle/configuration/tls/). This guide does not adopt that default.
How the Python client exposes local-development relaxation (an explicit option, a `skipTlsValidation`
connection-string parameter, or both) is a public API decision for
[connection-string parsing](https://github.com/Cratis/Chronicle.Python/issues/2). Do not decide it implicitly in
an implementation, and do not make relaxed validation the behavior for non-local connections. The connection-string grammar, including `skipTlsValidation`, `apiKey`, and `auth=none`, is in
[connection string elements](https://www.cratis.io/chronicle/building-a-client/connection-string-elements/).

### Check the kernel before writing client code

Confirm that the kernel issues tokens before debugging a client. With the kernel from [Local kernel](#local-kernel)
running:

```shell
curl --insecure https://localhost:35000/connect/token \
  -d grant_type=client_credentials \
  -d client_id=chronicle-dev-client \
  -d client_secret=chronicle-dev-secret
```

`--insecure` skips certificate validation and is only acceptable against this local development kernel. A working
kernel returns JSON with `access_token`, `token_type` (`Bearer`), and `expires_in`. A wrong secret returns HTTP 401.

The following probe exercises the same path through the generated contracts: it trusts the kernel's own
certificate, obtains a token, and calls `EnsureEventStore` once without and once with the bearer token. It is a
contributor diagnostic built on the internal contracts package, not the planned public client API.

```python
import asyncio
import json
import ssl
import urllib.parse
import urllib.request

import grpc
from cratis_chronicle_contracts.eventstores_pb2 import EnsureEventStoreRequest
from cratis_chronicle_contracts.eventstores_pb2_grpc import EventStoresStub

HOST, PORT = "localhost", 35000

# Development only: trust whatever certificate the local kernel presents.
certificate = ssl.get_server_certificate((HOST, PORT))
body = urllib.parse.urlencode(
    {
        "grant_type": "client_credentials",
        "client_id": "chronicle-dev-client",
        "client_secret": "chronicle-dev-secret",
    }
).encode()
request = urllib.request.Request(f"https://{HOST}:{PORT}/connect/token", data=body)
with urllib.request.urlopen(request, context=ssl.create_default_context(cadata=certificate)) as response:
    token = json.load(response)["access_token"]


async def main() -> None:
    credentials = grpc.ssl_channel_credentials(root_certificates=certificate.encode())
    async with grpc.aio.secure_channel(f"{HOST}:{PORT}", credentials) as channel:
        event_stores = EventStoresStub(channel)
        try:
            await event_stores.EnsureEventStore(EnsureEventStoreRequest(Name="python-probe"))
        except grpc.aio.AioRpcError as error:
            print("without token:", error.code().name)
        result = await event_stores.EnsureEventStore(
            EnsureEventStoreRequest(Name="python-probe"),
            metadata=[("authorization", f"Bearer {token}")],
        )
        print("with token:", type(result).__name__)


asyncio.run(main())
```

Run it from the activated development environment. Against `cratis/chronicle:16.38.2-development` it prints:

```text
without token: UNAUTHENTICATED
with token: CommandResult
```

The probe creates an event store named `python-probe` in the development kernel. Stopping the container removes it.

## First executable milestone

Implement and verify this order before expanding the API:

1. Parse explicit connection options.
2. Establish the TLS gRPC channel.
3. Obtain and propagate a bearer token.
4. Ensure one event store.
5. Ensure its namespace; use `Default` for the first exercise.
6. Register one event type and a non-empty JSON schema.
7. Append one event to `event-log`.
8. Assert that the response reports success and a sequence number.
9. Close the channel and token resources deterministically.

Stop there. Projections, reducers, reactors, subscriptions, automatic artifact discovery, reconnect behavior, and
framework integrations each add ordering or lifecycle behavior and should have separate evidence.

## Suggested module boundaries

The final names are subject to API review, but contributions should keep these responsibilities separate:

- public connection options and validation;
- OAuth token acquisition and refresh;
- gRPC channel creation and metadata interception;
- generated-stub access behind an internal service registry;
- wire-value conversion;
- event-store and namespace setup;
- event-type/schema registration; and
- event-log append/read operations.

Do not create one large client class that owns every responsibility.

## Wire-value conformance

The core Chronicle repository owns the value contract. Initial conversion tests must cover at least:

- UUIDs as canonical strings;
- dates and times in the documented Chronicle forms;
- Chronicle's duration form;
- concept wrappers serialized as their primitive value;
- exact schema and payload property naming; and
- a non-empty schema for a registered event type.

Cross-client implementation similarity is useful evidence, but another client is not protocol authority. Resolve
uncertainty against the core contracts and kernel behavior.

## Definition of done for a milestone

- The public API was discussed or accepted in its issue.
- Unit tests cover success and relevant failure behavior.
- An integration test exercises the exact kernel profile when network behavior changes.
- Local quality gates and CI pass.
- Documentation names unsupported behavior and development-only exceptions.
- No compatibility, parity, support, security, performance, or maturity claim was added without approval.

## Troubleshooting

| Symptom | Likely cause and fix |
| --- | --- |
| `pip install -e ".[dev]"` fails while downloading `cratis_chronicle_contracts-16.38.2-py3-none-any.whl` | The install cannot reach GitHub release assets. Allow `github.com` and `release-assets.githubusercontent.com`, where the download redirects, through your proxy or firewall |
| `pip` reports that hashes do not match | The downloaded wheel differs from the pinned SHA-256. Do not remove the hash; report it in an issue |
| `docker run` fails with `port is already allocated` | Another Chronicle kernel or process uses port 35000. Stop it, or publish a different host port (`-p 127.0.0.1:35100:35000`) and use that port in the connection string, the `curl` URL, and the probe's `PORT` |
| `ssl.SSLEOFError` or a refused connection right after `docker run` | The kernel is still starting. Wait until the token check succeeds, then retry |
| gRPC `UNAVAILABLE` with `CERTIFICATE_VERIFY_FAILED` in the details | The channel does not trust the kernel's self-signed certificate. Trust it explicitly for local development, as the probe does |
| gRPC `UNAUTHENTICATED` | The call carried no `authorization` metadata, or its token expired. Obtain a fresh token and attach it to every call |

## Next steps

- Pick up [connection-string parsing](https://github.com/Cratis/Chronicle.Python/issues/2), then
  [async OAuth token handling](https://github.com/Cratis/Chronicle.Python/issues/3).
- Read Chronicle's [Building a Chronicle client](https://www.cratis.io/chronicle/building-a-client/) guide for
  the cross-client contract.
- Follow [CONTRIBUTING.md](../CONTRIBUTING.md) for the required checks before opening a pull request.
