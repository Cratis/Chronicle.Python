---
title: Getting started
description: Install the experimental Chronicle Python client from a source checkout, authenticate to a local development kernel and append your first event.
---

This client is experimental. Its API changes without notice, nothing is published to PyPI, and it supports one
workflow: connect, authenticate, ensure an event store and namespace, register an event type and append an event.
Projections, reducers, reactors, subscriptions, reconnect handling and automatic kernel discovery are not
implemented.

## Install from a source checkout

Python 3.10 or newer is required. The install downloads the generated contracts wheel from GitHub release assets.

```shell
git clone https://github.com/Cratis/Chronicle.Python.git
cd Chronicle.Python
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Start a development kernel

The contracts in this client are generated from Chronicle 19.31.3, so use the matching kernel image. The development
image generates a self-signed certificate, accepts the built-in development credentials and keeps events inside the
container.

```shell
docker run --rm -p 127.0.0.1:35000:35000 cratis/chronicle:19.31.3-development
```

:::caution[Older kernels are not supported]
The client calls the 19.x gRPC contracts. Against a 16.x kernel, such as `cratis/chronicle:16.38.2-development`,
ensuring an event store and a namespace works but registering an event type fails with `UNIMPLEMENTED`, because the
kernel renamed that contract. Use a 19.31.3 or compatible kernel.
:::

## Append an event

```python
import asyncio
import uuid

from cratis_chronicle import ChronicleClient, EventTypeDefinition

BOOK_ADDED = EventTypeDefinition(
    id="book-added",
    schema={
        "type": "object",
        "properties": {"title": {"type": "string"}, "isbn": {"type": "string"}},
        "required": ["title", "isbn"],
    },
)


async def main() -> None:
    async with await ChronicleClient.connect("chronicle://localhost:35000") as client:
        event_store = await client.ensure_event_store("library")
        namespace = await event_store.ensure_namespace("Default")
        await event_store.register_event_type(BOOK_ADDED)

        result = await namespace.event_log.append(
            event_source_id=str(uuid.uuid4()),
            event_type=BOOK_ADDED,
            content={"title": "Event Sourcing in Python", "isbn": "978-0-00-000000-0"},
        )
        print(result.sequence_number)


asyncio.run(main())
```

The same program ships as [`Samples/append_event/main.py`](../Samples/README.md). Leaving the `async with` block
closes the gRPC channel and the token provider.

## Authentication and TLS

The client requests an OAuth token with the credentials from the connection string and attaches it to every new gRPC
call. See [Connection strings](connection-strings.md) for the credentials, and
[Authentication and TLS](authentication-and-tls.md) for token refresh, certificate trust and error handling.

## Errors

| Error | Meaning |
| --- | --- |
| `TokenAuthorizationError` | The token endpoint rejected the client credentials |
| `TokenRequestError` | The token request failed: network, TLS, timeout or an unexpected status |
| `TokenResponseError` | The token endpoint returned something that is not a token response |
| `CommandFailedError` | The kernel reported a failure while ensuring an event store or namespace |
| `AppendFailedError` | The kernel did not append the event |

All of them derive from `ChronicleError`. No message contains the client secret or an access token.

## What works today

| You want to… | Status |
| --- | --- |
| `pip install cratis-chronicle` from PyPI | Not possible. No package is published |
| Authenticate, ensure state, register an event type and append | Supported against a 19.31.3 development kernel |
| Read events, observe, project or react | Not implemented |
| Reconnect or discover a kernel automatically | Not implemented |
| Use Chronicle from another language now | Use the [.NET](https://github.com/Cratis/Chronicle), [TypeScript](https://github.com/Cratis/Chronicle.TypeScript), [Kotlin/Java](https://github.com/Cratis/Chronicle.Kotlin), or [Elixir](https://github.com/Cratis/Chronicle.Elixir) client |
