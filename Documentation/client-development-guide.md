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

## Local kernel

The development kernel listens on `localhost:35000`. Its main listener uses TLS and serves gRPC over HTTP/2. A
development build creates a self-signed certificate and built-in client credentials.

Start the development image:

```shell
docker run --rm -p 35000:35000 cratis/chronicle:latest-development
```

Use the explicit local-development connection string:

```text
chronicle://chronicle-dev-client:chronicle-dev-secret@localhost:35000
```

These credentials are development defaults only. They are not production credentials or a production
configuration contract.

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

Parse `access_token` from the JSON response. Attach the current token to each new gRPC call as metadata:

```text
authorization: Bearer <access token>
```

Token acquisition, caching, expiry, refresh, and call interception should remain separate from the channel. Do
not permanently bake one expiring token into channel headers.

The development kernel uses a self-signed certificate. A development option may explicitly relax certificate
verification for localhost. Production behavior must retain normal certificate and hostname validation.

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
