# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

"""An in-process gRPC server that stands in for the kernel services the client uses."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import grpc
from cratis_chronicle_contracts import (
    eventstores_pb2,
    eventstores_pb2_grpc,
    eventtypes_pb2,
    eventtypes_pb2_grpc,
    namespaces_pb2,
    namespaces_pb2_grpc,
    sequences_pb2,
    sequences_pb2_grpc,
)
from grpc import aio

from cratis_chronicle import HttpResponse


@dataclass
class FakeKernel:
    calls: list[str] = field(default_factory=list)
    metadata: list[Mapping[str, str]] = field(default_factory=list)
    appended: list[Any] = field(default_factory=list)
    registered: list[Any] = field(default_factory=list)
    append_errors: list[str] = field(default_factory=list)
    namespace_failure: str | None = None
    register_failure: str | None = None
    next_sequence_number: int = 42
    port: int = 0
    _server: aio.Server | None = None

    def record(self, name: str, context: aio.ServicerContext) -> None:
        self.calls.append(name)
        self.metadata.append({key: value for key, value in context.invocation_metadata()})

    async def start(self) -> None:
        kernel = self

        class EventStores(eventstores_pb2_grpc.EventStoresServicer):
            async def EnsureEventStore(self, request: Any, context: aio.ServicerContext) -> Any:
                kernel.record(f"EnsureEventStore:{request.Name}", context)
                return eventstores_pb2.CommandResult()

        class Namespaces(namespaces_pb2_grpc.NamespacesServicer):
            async def EnsureNamespace(self, request: Any, context: aio.ServicerContext) -> Any:
                kernel.record(f"EnsureNamespace:{request.EventStore}/{request.Namespace}", context)
                result = namespaces_pb2.CommandResult()
                if kernel.namespace_failure:
                    result.ExceptionMessages.append(kernel.namespace_failure)
                return result

        class EventTypes(eventtypes_pb2_grpc.EventTypesServicer):
            async def RegisterEventTypes(self, request: Any, context: aio.ServicerContext) -> Any:
                kernel.record(f"RegisterEventTypes:{request.EventStore}", context)
                kernel.registered.extend(request.Types)
                result = eventtypes_pb2.CommandResult()
                if kernel.register_failure:
                    result.ExceptionMessages.append(kernel.register_failure)
                return result

        class EventSequences(sequences_pb2_grpc.EventSequencesServicer):
            async def Append(self, request: Any, context: aio.ServicerContext) -> Any:
                kernel.record("Append", context)
                kernel.appended.append(request)
                result = sequences_pb2.CommandResult_AppendResponse()
                result.Response.SequenceNumber = kernel.next_sequence_number
                result.Response.CorrelationId.CopyFrom(request.CorrelationId)
                result.Response.Errors.extend(kernel.append_errors)
                return result

        server = aio.server()
        eventstores_pb2_grpc.add_EventStoresServicer_to_server(EventStores(), server)
        namespaces_pb2_grpc.add_NamespacesServicer_to_server(Namespaces(), server)
        eventtypes_pb2_grpc.add_EventTypesServicer_to_server(EventTypes(), server)
        sequences_pb2_grpc.add_EventSequencesServicer_to_server(EventSequences(), server)
        self.port = server.add_insecure_port("127.0.0.1:0")
        self._server = server
        await server.start()

    async def stop(self) -> None:
        if self._server is not None:
            await self._server.stop(None)

    def content_of_appended(self, index: int = 0) -> Any:
        return json.loads(self.appended[index].Content)


class FakeTokenTransport:
    """Hands out numbered tokens, so a test can see which token each call carried."""

    def __init__(self, *, fail_with: BaseException | None = None, expires_in: float | None = 3600) -> None:
        self.requests = 0
        self._fail_with = fail_with
        self._expires_in = expires_in

    async def post_form(self, url: str, fields: Mapping[str, str]) -> HttpResponse:
        self.requests += 1
        if self._fail_with is not None:
            raise self._fail_with
        body: dict[str, Any] = {"access_token": f"token-{self.requests}", "token_type": "Bearer"}
        if self._expires_in is not None:
            body["expires_in"] = self._expires_in
        return HttpResponse(200, json.dumps(body).encode())


__all__ = ["FakeKernel", "FakeTokenTransport", "grpc"]
