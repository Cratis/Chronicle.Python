# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

import asyncio
import datetime
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import grpc
import pytest
from fake_kernel import FakeKernel, FakeTokenTransport

from cratis_chronicle import (
    AppendFailedError,
    ChronicleChannel,
    ChronicleClient,
    ChronicleConnectionOptions,
    CommandFailedError,
    EventTypeDefinition,
    TokenRequestError,
)

BOOK_ADDED = EventTypeDefinition(
    id="book-added", schema={"type": "object", "properties": {"title": {"type": "string"}}}
)


def with_kernel(
    scenario: Callable[[FakeKernel, ChronicleClient, FakeTokenTransport], Awaitable[Any]],
    transport: FakeTokenTransport | None = None,
    kernel: FakeKernel | None = None,
) -> Any:
    async def run() -> Any:
        fake = kernel or FakeKernel()
        tokens = transport or FakeTokenTransport()
        await fake.start()
        try:
            options = ChronicleConnectionOptions(
                host="127.0.0.1", client_id="id", client_secret="secret", port=fake.port, tls=False
            )
            channel = await ChronicleChannel.open(options, token_transport=tokens)
            async with ChronicleClient(channel) as client:
                return await scenario(fake, client, tokens)
        finally:
            await fake.stop()

    return asyncio.run(run())


def test_establishes_state_in_order_registers_a_schema_and_appends_to_the_event_log() -> None:
    async def scenario(kernel: FakeKernel, client: ChronicleClient, _: FakeTokenTransport) -> Any:
        store = await client.ensure_event_store("books")
        namespace = await store.ensure_namespace()
        await store.register_event_type(BOOK_ADDED)
        source = str(uuid.uuid4())
        return source, await namespace.event_log.append(source, BOOK_ADDED, {"title": "Dune"})

    kernel = FakeKernel()
    source, result = with_kernel(scenario, kernel=kernel)

    assert kernel.calls == ["EnsureEventStore:books", "EnsureNamespace:books/Default", "Register:books", "Append"]
    registration = kernel.registered[0]
    assert (registration.Type.Id, registration.Type.Generation) == ("book-added", 1)
    assert '"properties"' in registration.Schema
    request = kernel.appended[0]
    assert (request.EventStore, request.Namespace, request.EventSequenceId) == ("books", "Default", "event-log")
    assert request.EventSourceId == source
    assert (request.EventType.Id, request.EventType.Generation) == ("book-added", 1)
    assert kernel.content_of_appended() == {"title": "Dune"}
    assert request.ConcurrencyScope.SequenceNumber == 2**64 - 1
    assert len(request.Causation) == 1
    assert result.sequence_number == 42
    assert result.correlation_id.int != 0


def test_every_call_carries_the_current_bearer_token() -> None:
    async def scenario(kernel: FakeKernel, client: ChronicleClient, _: FakeTokenTransport) -> None:
        store = await client.ensure_event_store("books")
        await store.ensure_namespace()

    kernel, transport = FakeKernel(), FakeTokenTransport()
    with_kernel(scenario, transport, kernel)

    assert [entry["authorization"] for entry in kernel.metadata] == ["Bearer token-1", "Bearer token-1"]
    assert transport.requests == 1


def test_a_refreshed_token_is_used_for_the_next_new_call() -> None:
    async def scenario(kernel: FakeKernel, client: ChronicleClient, _: FakeTokenTransport) -> None:
        await client.ensure_event_store("a")
        await asyncio.sleep(0.05)
        await client.ensure_event_store("b")

    kernel = FakeKernel()
    with_kernel(scenario, FakeTokenTransport(expires_in=0.05), kernel)

    assert [entry["authorization"] for entry in kernel.metadata] == ["Bearer token-1", "Bearer token-2"]


def test_a_token_failure_surfaces_as_a_token_error_and_nothing_reaches_the_kernel() -> None:
    async def scenario(kernel: FakeKernel, client: ChronicleClient, _: FakeTokenTransport) -> None:
        await client.ensure_event_store("books")

    kernel = FakeKernel()
    transport = FakeTokenTransport(fail_with=TokenRequestError("endpoint down"))

    with pytest.raises(TokenRequestError, match="endpoint down"):
        with_kernel(scenario, transport, kernel)

    assert kernel.calls == []


def test_a_failed_command_result_raises_with_the_reason() -> None:
    async def scenario(kernel: FakeKernel, client: ChronicleClient, _: FakeTokenTransport) -> None:
        store = await client.ensure_event_store("books")
        await store.ensure_namespace()

    kernel = FakeKernel(namespace_failure="boom")

    with pytest.raises(CommandFailedError, match="boom") as raised:
        with_kernel(scenario, kernel=kernel)

    assert raised.value.reasons == ["boom"]


def test_kernel_append_errors_raise_append_failed() -> None:
    async def scenario(kernel: FakeKernel, client: ChronicleClient, _: FakeTokenTransport) -> None:
        namespace = await (await client.ensure_event_store("books")).ensure_namespace()
        await namespace.event_log.append("src", BOOK_ADDED, {"title": "Dune"})

    with pytest.raises(AppendFailedError, match="schema mismatch"):
        with_kernel(scenario, kernel=FakeKernel(append_errors=["schema mismatch"]))


def test_invalid_inputs_are_rejected_before_anything_is_sent() -> None:
    async def scenario(kernel: FakeKernel, client: ChronicleClient, _: FakeTokenTransport) -> None:
        namespace = await (await client.ensure_event_store("books")).ensure_namespace()
        with pytest.raises(ValueError, match="event source id"):
            await namespace.event_log.append(" ", BOOK_ADDED, {})
        with pytest.raises(ValueError, match="timezone-aware"):
            await namespace.event_log.append("a", BOOK_ADDED, {}, occurred=datetime.datetime(2026, 1, 1))
        with pytest.raises(TypeError):
            await namespace.event_log.append("a", BOOK_ADDED, [1])

    kernel = FakeKernel()
    with_kernel(scenario, kernel=kernel)

    assert "Append" not in kernel.calls


def test_event_type_definitions_require_an_id_a_generation_and_a_non_empty_schema() -> None:
    with pytest.raises(ValueError, match="non-empty JSON schema"):
        EventTypeDefinition(id="x", schema={})
    with pytest.raises(ValueError, match="id"):
        EventTypeDefinition(id=" ", schema={"type": "object"})
    with pytest.raises(ValueError, match="generation"):
        EventTypeDefinition(id="x", schema={"type": "object"}, generation=0)


def test_closing_is_deterministic_and_idempotent() -> None:
    async def run() -> None:
        kernel = FakeKernel()
        await kernel.start()
        try:
            options = ChronicleConnectionOptions(
                host="127.0.0.1", client_id="id", client_secret="secret", port=kernel.port, tls=False
            )
            client = ChronicleClient(await ChronicleChannel.open(options, token_transport=FakeTokenTransport()))
            await client.ensure_event_store("books")
            await client.aclose()
            await client.aclose()
            with pytest.raises((grpc.aio.UsageError, TokenRequestError)):
                await client.ensure_event_store("books")
        finally:
            await kernel.stop()

    asyncio.run(run())


def test_connect_accepts_a_connection_string() -> None:
    async def run() -> None:
        client = await ChronicleClient.connect("chronicle://id:secret@localhost:1/?skipTlsValidation=false")
        await client.aclose()

    asyncio.run(run())


def test_credentials_are_not_sent_without_tls_to_a_remote_host() -> None:
    from cratis_chronicle import ChronicleChannel, ChronicleConnectionOptions, InsecureTransportError

    options = ChronicleConnectionOptions(host="kernel.example.com", client_id="id", client_secret="secret", tls=False)
    with pytest.raises(InsecureTransportError):
        asyncio.run(ChronicleChannel.open(options))
