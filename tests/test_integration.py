# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

"""Opt-in checks against a real kernel. Skipped unless CHRONICLE_INTEGRATION_URL names one.

Set it to the connection string of a *development* kernel you started for this purpose, for example
``CHRONICLE_INTEGRATION_URL=chronicle://localhost:19300``. See Documentation/client-development-guide.md.
"""

import asyncio
import os
import uuid
from urllib.parse import urlsplit

import pytest

from cratis_chronicle import (
    AppendFailedError,
    ChronicleClient,
    EventTypeDefinition,
    TokenAuthorizationError,
    TokenError,
)

URL = os.environ.get("CHRONICLE_INTEGRATION_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(URL is None, reason="CHRONICLE_INTEGRATION_URL is not set"),
]

EVENT_TYPE = EventTypeDefinition(
    id="python-integration.book-added",
    schema={"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]},
)


def endpoint() -> str:
    assert URL is not None
    parts = urlsplit(URL)
    return f"{parts.hostname}:{parts.port}"


def test_authenticates_establishes_state_registers_and_appends_to_the_event_log() -> None:
    async def scenario() -> tuple[int, int]:
        assert URL is not None
        async with await ChronicleClient.connect(URL) as client:
            store = await client.ensure_event_store("python-integration")
            namespace = await store.ensure_namespace("Default")
            await store.register_event_type(EVENT_TYPE)
            source = str(uuid.uuid4())
            first = await namespace.event_log.append(source, EVENT_TYPE, {"title": "first"})
            second = await namespace.event_log.append(source, EVENT_TYPE, {"title": "second"})
            return first.sequence_number, second.sequence_number

    first, second = asyncio.run(scenario())

    assert first >= 0
    assert second == first + 1


def test_content_that_violates_the_registered_schema_is_not_appended() -> None:
    async def scenario() -> None:
        assert URL is not None
        async with await ChronicleClient.connect(URL) as client:
            store = await client.ensure_event_store("python-integration")
            namespace = await store.ensure_namespace("Default")
            await store.register_event_type(EVENT_TYPE)
            await namespace.event_log.append(str(uuid.uuid4()), EVENT_TYPE, {"unexpected": 1})

    with pytest.raises(AppendFailedError, match="title"):
        asyncio.run(scenario())


def test_wrong_credentials_fail_with_a_token_authorization_error_that_does_not_leak_the_secret() -> None:
    secret = "definitely-the-wrong-secret"  # noqa: S105

    async def scenario() -> None:
        async with await ChronicleClient.connect(f"chronicle://chronicle-dev-client:{secret}@{endpoint()}") as client:
            await client.ensure_event_store("python-integration")

    with pytest.raises(TokenAuthorizationError) as raised:
        asyncio.run(scenario())

    assert secret not in str(raised.value)
    assert secret not in repr(raised.value)


def test_a_self_signed_kernel_certificate_is_rejected_when_validation_is_required() -> None:
    async def scenario() -> None:
        async with await ChronicleClient.connect(f"chronicle://{endpoint()}/?skipTlsValidation=false") as client:
            await client.ensure_event_store("python-integration")

    with pytest.raises(TokenError, match="TLS handshake"):
        asyncio.run(scenario())
