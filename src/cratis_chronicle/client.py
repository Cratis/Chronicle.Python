# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

"""The Chronicle client: connect, ensure an event store and namespace, register an event type and append."""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Iterable
from typing import Any

from cratis_chronicle_contracts.events_pb2 import EventType as RegistrationEventType
from cratis_chronicle_contracts.events_pb2 import EventTypeRegistration, RegisterEventTypesRequest
from cratis_chronicle_contracts.events_pb2_grpc import EventTypesStub
from cratis_chronicle_contracts.eventstores_pb2 import EnsureEventStoreRequest
from cratis_chronicle_contracts.eventstores_pb2_grpc import EventStoresStub
from cratis_chronicle_contracts.namespaces_pb2 import EnsureNamespaceRequest
from cratis_chronicle_contracts.namespaces_pb2_grpc import NamespacesStub

from . import _eventsequence_contracts as sequence_contracts
from .channel import ChronicleChannel
from .connection_string import ChronicleConnectionOptions, parse_connection_string
from .errors import AppendFailedError, CommandFailedError
from .events import AppendResult, EventTypeDefinition
from .wire import from_wire_guid, serialize_content, to_wire_guid, to_wire_timestamp

__all__ = ["DEFAULT_NAMESPACE", "EVENT_LOG", "ChronicleClient", "EventSequence", "EventStore", "Namespace"]

DEFAULT_NAMESPACE = "Default"
EVENT_LOG = "event-log"
_ERROR_SEVERITY = 3
UNAVAILABLE_SEQUENCE_NUMBER = 2**64 - 1
CAUSATION_TYPE = "Python Client"
IDENTITY = "cratis-chronicle-python"


def _ensure_command_succeeded(operation: str, result: Any) -> None:
    reasons = [message for message in result.ExceptionMessages]
    reasons += [validation.Message for validation in result.ValidationResults if validation.Severity == _ERROR_SEVERITY]
    # IsAuthorized is not consulted: the contract defaults it to true, so the kernel omits it for success and proto3
    # reads that as false. An authorization failure carries its reason.
    if result.AuthorizationFailureReason:
        reasons.append(result.AuthorizationFailureReason)
    if reasons:
        raise CommandFailedError(operation, reasons)


class EventSequence:
    """An event sequence of one namespace, such as the event log."""

    def __init__(self, stub: Any, event_store: str, namespace: str, sequence_id: str) -> None:
        self._stub = stub
        self._event_store = event_store
        self._namespace = namespace
        self._sequence_id = sequence_id

    async def append(
        self,
        event_source_id: str,
        event_type: EventTypeDefinition,
        content: Any,
        *,
        occurred: datetime.datetime | None = None,
    ) -> AppendResult:
        """Append one event and return its sequence number.

        ``content`` is a mapping or dataclass whose property names must match the registered schema. The event type
        must have been registered with :meth:`EventStore.register_event_type`.

        Raises:
            AppendFailedError: The kernel reported errors, a constraint violation or a concurrency violation.
        """
        if not event_source_id.strip():
            raise ValueError("An event source id must not be empty")
        correlation_id = uuid.uuid4()
        timestamp = sequence_contracts.messages.SerializableDateTimeOffset(
            Value=to_wire_timestamp(occurred or datetime.datetime.now(datetime.timezone.utc))
        )
        request = sequence_contracts.messages.AppendRequest(
            EventStore=self._event_store,
            Namespace=self._namespace,
            EventSequenceId=self._sequence_id,
            CorrelationId=to_wire_guid(correlation_id),
            EventSourceId=event_source_id,
            EventType=sequence_contracts.messages.EventType(Id=event_type.id, Generation=event_type.generation),
            Content=serialize_content(content),
            # The kernel dereferences the causation chain, so an empty chain fails the call; record who appended.
            Causation=[sequence_contracts.messages.Causation(Occurred=timestamp, Type=CAUSATION_TYPE)],
            CausedBy=sequence_contracts.messages.Identity(Subject=IDENTITY, Name=IDENTITY, UserName=IDENTITY),
            Occurred=timestamp,
        )
        # An unset scope makes the kernel dereference null, and sequence number 0 would demand an empty sequence.
        # The unavailable sequence number is the value the kernel does not validate.
        request.ConcurrencyScope.SequenceNumber = UNAVAILABLE_SEQUENCE_NUMBER
        response = await self._stub.Append(request)
        reasons = list(response.Errors)
        reasons += [f"constraint violation: {violation.Message}" for violation in response.ConstraintViolations]
        if response.HasField("ConcurrencyViolation"):
            reasons.append("concurrency violation")
        if reasons:
            raise AppendFailedError(reasons)
        return AppendResult(
            sequence_number=response.SequenceNumber, correlation_id=from_wire_guid(response.CorrelationId)
        )


class Namespace:
    """A namespace of an event store."""

    def __init__(self, channel: ChronicleChannel, event_store: str, name: str) -> None:
        self.name = name
        self._event_log = EventSequence(
            sequence_contracts.services.EventSequencesStub(channel.channel), event_store, name, EVENT_LOG
        )

    @property
    def event_log(self) -> EventSequence:
        """The default event sequence."""
        return self._event_log


class EventStore:
    """An event store that exists in the kernel."""

    def __init__(self, channel: ChronicleChannel, name: str) -> None:
        self.name = name
        self._channel = channel

    async def ensure_namespace(self, name: str = DEFAULT_NAMESPACE) -> Namespace:
        """Create the namespace when it does not exist yet and return it."""
        result = await NamespacesStub(self._channel.channel).EnsureNamespace(
            EnsureNamespaceRequest(EventStore=self.name, Namespace=name)
        )
        _ensure_command_succeeded(f"Ensuring namespace '{name}'", result)
        return Namespace(self._channel, self.name, name)

    async def register_event_types(self, definitions: Iterable[EventTypeDefinition]) -> None:
        """Register event types with their schemas in this event store."""
        registrations = [
            EventTypeRegistration(
                Type=RegistrationEventType(Id=definition.id, Generation=definition.generation),
                Schema=definition.schema_json(),
            )
            for definition in definitions
        ]
        await EventTypesStub(self._channel.channel).Register(
            RegisterEventTypesRequest(EventStore=self.name, Types=registrations)
        )

    async def register_event_type(self, definition: EventTypeDefinition) -> None:
        """Register one event type with its schema in this event store."""
        await self.register_event_types([definition])


class ChronicleClient:
    """An experimental async client for a Chronicle kernel. Use it as an async context manager."""

    def __init__(self, channel: ChronicleChannel) -> None:
        self._channel = channel

    @classmethod
    async def connect(
        cls,
        connection: str | ChronicleConnectionOptions,
        *,
        ca_certificates: bytes | None = None,
    ) -> ChronicleClient:
        """Create a client from a connection string or options. See :class:`ChronicleChannel` for the TLS rules."""
        options = parse_connection_string(connection) if isinstance(connection, str) else connection
        return cls(await ChronicleChannel.open(options, ca_certificates=ca_certificates))

    async def ensure_event_store(self, name: str) -> EventStore:
        """Create the event store when it does not exist yet and return it."""
        result = await EventStoresStub(self._channel.channel).EnsureEventStore(EnsureEventStoreRequest(Name=name))
        _ensure_command_succeeded(f"Ensuring event store '{name}'", result)
        return EventStore(self._channel, name)

    async def aclose(self) -> None:
        """Close the channel and the token provider. Safe to call more than once."""
        await self._channel.aclose()

    async def __aenter__(self) -> ChronicleClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
