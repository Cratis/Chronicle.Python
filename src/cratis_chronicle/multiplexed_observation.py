# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.
"""Observe every reactor and reducer of a connection over one shared bidirectional gRPC stream."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable
from typing import Any, Final

import grpc
from cratis_chronicle_contracts import (
    observation_multiplexed_pb2 as multiplexed,
)
from cratis_chronicle_contracts import (
    observation_reactors_pb2 as reactors,
)
from cratis_chronicle_contracts import (
    observation_reducers_pb2 as reducers,
)

#: The capability the kernel advertises from ``CheckCompatibility`` when it serves the multiplexed stream.
MULTIPLEXED_OBSERVATION_CAPABILITY: Final = "multiplexed-observation"

#: How long messages are collected before they are written together.
COALESCE_SECONDS: Final = 0.01

#: The most messages written in one ``MultiplexedClientMessage``.
MAX_MESSAGES_PER_WRITE: Final = 500

_STATUS_CODES: Final = {code.value[0]: code for code in grpc.StatusCode}


def use_multiplexed_observation(capabilities: object, *, enabled: bool = True) -> bool:
    """Decide whether observers share one stream.

    Multiplexing is used only when the option is on and the kernel advertised the capability. Anything else
    (capability absent, option off, compatibility check skipped) keeps one stream per observer.
    """
    if not enabled or capabilities is None:
        return False
    return MULTIPLEXED_OBSERVATION_CAPABILITY in capabilities  # type: ignore[operator]


class MultiplexedStreamSequenceError(Exception):
    """Raised on every open stream when the kernel skipped or repeated a message of one stream."""


def _end_to_error(end: Any) -> grpc.aio.AioRpcError:
    code = _STATUS_CODES.get(end.StatusCode, grpc.StatusCode.UNKNOWN)
    return grpc.aio.AioRpcError(code, grpc.aio.Metadata(), grpc.aio.Metadata(), end.Detail)


class _Completed:
    pass


_COMPLETED: Final = _Completed()


class _Stream:
    def __init__(self, stream_id: int) -> None:
        self.stream_id = stream_id
        self.expected_sequence = 1
        # Unbounded: a slow observer buffers here and never blocks the reader loop or the other streams.
        self.inbox: asyncio.Queue[object] = asyncio.Queue()
        self.ended = False
        self.close_sent = False


class _SharedCall:
    """One shared kernel call: the writer feeds it, the reader task demultiplexes it."""

    def __init__(
        self, open_call: Callable[[AsyncIterator[Any]], Any], on_finished: Callable[[_SharedCall], None]
    ) -> None:
        self.outgoing: asyncio.Queue[Any] = asyncio.Queue()
        self.streams: dict[int, _Stream] = {}
        self._on_finished = on_finished
        self._call = open_call(self._writes())
        self._reader = asyncio.create_task(self._read())

    async def _writes(self) -> AsyncIterator[Any]:
        while True:
            first = await self.outgoing.get()
            if first is None:
                return
            await asyncio.sleep(COALESCE_SECONDS)
            batch = [first]
            finished = False
            while len(batch) < MAX_MESSAGES_PER_WRITE and not self.outgoing.empty():
                message = self.outgoing.get_nowait()
                if message is None:
                    finished = True
                    break
                batch.append(message)
            yield multiplexed.MultiplexedClientMessage(Messages=batch)
            if finished:
                return

    async def _read(self) -> None:
        failure: BaseException | None = None
        try:
            async for message in self._call:
                self._deliver(message)
        except asyncio.CancelledError:
            raise
        except BaseException as error:  # every failure of the shared call fails every stream
            failure = error
        self._finish(failure)

    def _deliver(self, message: Any) -> None:
        stream = self.streams.get(message.StreamId)
        if stream is None:
            return
        if message.Sequence != stream.expected_sequence:
            raise MultiplexedStreamSequenceError(
                f"Stream {stream.stream_id} expected sequence {stream.expected_sequence} "
                f"but received {message.Sequence}"
            )
        stream.expected_sequence += 1
        if message.HasField("End"):
            stream.ended = True
            self.streams.pop(stream.stream_id, None)
            stream.inbox.put_nowait(_COMPLETED if message.End.StatusCode == 0 else _end_to_error(message.End))
        elif message.HasField("Reactor"):
            stream.inbox.put_nowait(message.Reactor)
        elif message.HasField("Reducer"):
            stream.inbox.put_nowait(message.Reducer)

    def _finish(self, failure: BaseException | None) -> None:
        self._on_finished(self)
        with contextlib.suppress(Exception):
            self._call.cancel()
        for stream in list(self.streams.values()):
            stream.ended = True
            stream.inbox.put_nowait(failure if failure is not None else _COMPLETED)
        self.streams.clear()

    def close(self) -> None:
        self._reader.cancel()
        self.outgoing.put_nowait(None)
        with contextlib.suppress(Exception):
            self._call.cancel()


class MultiplexedObservationChannel:
    """Shares one kernel call between all reactors and reducers of a connection.

    The call is opened by the first observer and cancelled when the last one closes; an observer that starts
    after the call failed gets a new call. ``observe_reactor`` and ``observe_reducer`` have the same shape as the
    per-observer ``Reactors.Observe`` and ``Reducers.Observe`` calls, so they drop in underneath them.
    """

    def __init__(self, open_call: Callable[[AsyncIterator[Any]], Any]) -> None:
        """Create the channel.

        Args:
            open_call: Starts the shared bidirectional call, e.g. ``MultiplexedObservationStub(channel).Observe``.
        """
        self._open_call = open_call
        self._shared: _SharedCall | None = None
        self._next_stream_id = 1

    def observe_reactor(self, requests: AsyncIterator[Any]) -> AsyncIterator[reactors.EventsToObserve]:
        """Observe as a reactor. ``requests`` yields the registration first, then results."""
        return self._observe(multiplexed.Reactor, requests, "Reactor", reactors.EventsToObserve)

    def observe_reducer(self, requests: AsyncIterator[Any]) -> AsyncIterator[reducers.ReduceOperationMessage]:
        """Observe as a reducer. ``requests`` yields the registration first, then results."""
        return self._observe(multiplexed.Reducer, requests, "Reducer", reducers.ReduceOperationMessage)

    async def _observe(
        self, kind: Any, requests: AsyncIterator[Any], field: str, response_type: Any
    ) -> AsyncIterator[Any]:
        shared = self._shared
        if shared is None:
            shared = self._shared = _SharedCall(self._open_call, self._finished)
        stream = _Stream(self._next_stream_id)
        self._next_stream_id += 1
        shared.streams[stream.stream_id] = stream
        pump = asyncio.create_task(self._forward_or_fail(shared, stream, kind, requests, field))
        try:
            while True:
                item = await stream.inbox.get()
                if item is _COMPLETED:
                    return
                if isinstance(item, BaseException):
                    raise item
                yield _convert(item, response_type)
        finally:
            pump.cancel()
            if not stream.ended and not stream.close_sent:
                stream.close_sent = True
                shared.outgoing.put_nowait(multiplexed.MultiplexedStreamMessage(StreamId=stream.stream_id, Close=True))
            shared.streams.pop(stream.stream_id, None)
            if not shared.streams and self._shared is shared:
                self._shared = None
                shared.close()

    async def _forward(
        self, shared: _SharedCall, stream: _Stream, kind: Any, requests: AsyncIterator[Any], field: str
    ) -> None:
        first = True
        async for request in requests:
            message = multiplexed.MultiplexedStreamMessage(StreamId=stream.stream_id)
            if first:
                message.Kind = kind
                first = False
            getattr(message, field).ParseFromString(request.SerializeToString())
            shared.outgoing.put_nowait(message)
        if not stream.ended and not stream.close_sent:
            stream.close_sent = True
            shared.outgoing.put_nowait(multiplexed.MultiplexedStreamMessage(StreamId=stream.stream_id, Close=True))

    async def _forward_or_fail(
        self, shared: _SharedCall, stream: _Stream, kind: Any, requests: AsyncIterator[Any], field: str
    ) -> None:
        try:
            await self._forward(shared, stream, kind, requests, field)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            stream.inbox.put_nowait(error)

    def _finished(self, shared: _SharedCall) -> None:
        if self._shared is shared:
            self._shared = None


def _convert(message: Any, response_type: Any) -> Any:
    converted = response_type()
    converted.ParseFromString(message.SerializeToString())
    return converted
