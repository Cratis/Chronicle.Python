# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.
import asyncio
from collections.abc import AsyncIterator, Awaitable
from typing import Any, TypeVar

import grpc
import pytest
from cratis_chronicle_contracts import observation_multiplexed_pb2 as multiplexed
from cratis_chronicle_contracts import observation_reactors_pb2 as reactors
from cratis_chronicle_contracts import observation_reducers_pb2 as reducers

from cratis_chronicle.multiplexed_observation import (
    MultiplexedObservationChannel,
    MultiplexedStreamSequenceError,
    use_multiplexed_observation,
)

T = TypeVar("T")


def run(awaitable: Awaitable[T]) -> T:
    async def bounded() -> T:
        return await asyncio.wait_for(awaitable, 5)

    return asyncio.run(bounded())


class FakeKernelCall:
    """Stands in for the shared call: records what the client wrote and lets the test push server messages."""

    def __init__(self, writes: AsyncIterator[Any]) -> None:
        self.written: list[Any] = []
        self.cancelled = False
        self._down: asyncio.Queue[Any] = asyncio.Queue()
        self._pump = asyncio.create_task(self._record(writes))

    async def _record(self, writes: AsyncIterator[Any]) -> None:
        async for write in writes:
            self.written.append(write)

    @property
    def messages(self) -> list[Any]:
        return [message for write in self.written for message in write.Messages]

    def send(self, stream_id: int, sequence: int, **fields: Any) -> None:
        self._down.put_nowait(multiplexed.MultiplexedServerMessage(StreamId=stream_id, Sequence=sequence, **fields))

    def end(self, stream_id: int, sequence: int, status: int = 0, detail: str = "") -> None:
        self.send(stream_id, sequence, End=multiplexed.MultiplexedStreamEnd(StatusCode=status, Detail=detail))

    def fail(self, error: BaseException) -> None:
        self._down.put_nowait(error)

    def cancel(self) -> None:
        self.cancelled = True
        self._pump.cancel()

    def __aiter__(self) -> "FakeKernelCall":
        return self

    async def __anext__(self) -> Any:
        item = await self._down.get()
        if isinstance(item, BaseException):
            raise item
        return item


class Kernel:
    def __init__(self) -> None:
        self.calls: list[FakeKernelCall] = []

    def open(self, writes: AsyncIterator[Any]) -> FakeKernelCall:
        call = FakeKernelCall(writes)
        self.calls.append(call)
        return call


async def registration_then_idle(registration: Any) -> AsyncIterator[Any]:
    yield registration
    await asyncio.Event().wait()


def reactor_registration(name: str) -> reactors.ReactorMessage:
    registration = reactors.RegisterReactor(ConnectionId=name)
    return reactors.ReactorMessage(Content=reactors.OneOf_RegisterReactor_ReactorResult(Value0=registration))


def reducer_registration(name: str) -> reducers.ReducerMessage:
    registration = reducers.RegisterReducer(ConnectionId=name)
    return reducers.ReducerMessage(Content=reducers.OneOf_RegisterReducer_ReducerResult(Value0=registration))


def events(partition: str) -> Any:
    return multiplexed.EventsToObserve(Partition=partition)


async def settle() -> None:
    await asyncio.sleep(0.05)


def start(channel: MultiplexedObservationChannel, registration: Any, *, reducer: bool = False) -> "asyncio.Queue[Any]":
    results: asyncio.Queue[Any] = asyncio.Queue()
    observe = channel.observe_reducer if reducer else channel.observe_reactor

    async def consume() -> None:
        try:
            async for item in observe(registration_then_idle(registration)):
                results.put_nowait(item)
            results.put_nowait("completed")
        except BaseException as error:
            results.put_nowait(error)

    asyncio.get_running_loop().create_task(consume())
    return results


def test_capability_present_and_option_on_multiplexes() -> None:
    assert use_multiplexed_observation(["multiplexed-observation"]) is True


def test_capability_absent_does_not_multiplex() -> None:
    assert use_multiplexed_observation([]) is False
    assert use_multiplexed_observation(None) is False


def test_option_off_does_not_multiplex() -> None:
    assert use_multiplexed_observation(["multiplexed-observation"], enabled=False) is False


def test_registrations_ready_together_are_written_once_and_only_the_first_message_has_a_kind() -> None:
    async def scenario() -> None:
        kernel = Kernel()
        channel = MultiplexedObservationChannel(kernel.open)
        start(channel, reactor_registration("a"))
        start(channel, reactor_registration("b"))
        start(channel, reducer_registration("c"), reducer=True)
        await settle()
        assert len(kernel.calls) == 1
        assert len(kernel.calls[0].written) == 1
        messages = kernel.calls[0].messages
        assert [m.StreamId for m in messages] == [1, 2, 3]
        assert [m.Kind for m in messages] == [multiplexed.Reactor, multiplexed.Reactor, multiplexed.Reducer]
        assert messages[0].Reactor.Content.Value0.ConnectionId == "a"
        assert messages[2].Reducer.Content.Value0.ConnectionId == "c"

    run(scenario())


def test_interleaved_messages_are_delivered_to_their_own_stream_in_order() -> None:
    async def scenario() -> None:
        kernel = Kernel()
        channel = MultiplexedObservationChannel(kernel.open)
        first = start(channel, reactor_registration("a"))
        second = start(channel, reducer_registration("b"), reducer=True)
        await settle()
        call = kernel.calls[0]
        call.send(1, 1, Reactor=events("a1"))
        call.send(2, 1, Reducer=multiplexed.ReduceOperationMessage())
        call.send(1, 2, Reactor=events("a2"))
        assert [(await first.get()).Partition, (await first.get()).Partition] == ["a1", "a2"]
        assert isinstance(await second.get(), reducers.ReduceOperationMessage)

    run(scenario())


def test_a_sequence_gap_fails_every_stream() -> None:
    async def scenario() -> None:
        kernel = Kernel()
        channel = MultiplexedObservationChannel(kernel.open)
        first = start(channel, reactor_registration("a"))
        second = start(channel, reactor_registration("b"))
        await settle()
        kernel.calls[0].send(1, 2, Reactor=events("skipped"))
        assert isinstance(await first.get(), MultiplexedStreamSequenceError)
        assert isinstance(await second.get(), MultiplexedStreamSequenceError)
        assert kernel.calls[0].cancelled

    run(scenario())


def test_a_stream_ending_with_a_status_fails_only_that_stream() -> None:
    async def scenario() -> None:
        kernel = Kernel()
        channel = MultiplexedObservationChannel(kernel.open)
        failing = start(channel, reactor_registration("a"))
        other = start(channel, reactor_registration("b"))
        await settle()
        call = kernel.calls[0]
        call.end(1, 1, status=grpc.StatusCode.UNAVAILABLE.value[0], detail="gone")
        error = await failing.get()
        assert isinstance(error, grpc.aio.AioRpcError)
        assert error.code() == grpc.StatusCode.UNAVAILABLE
        assert error.details() == "gone"
        call.send(2, 1, Reactor=events("still-here"))
        assert (await other.get()).Partition == "still-here"

    run(scenario())


def test_a_stream_ending_with_status_zero_completes() -> None:
    async def scenario() -> None:
        kernel = Kernel()
        results = start(MultiplexedObservationChannel(kernel.open), reactor_registration("a"))
        await settle()
        kernel.calls[0].end(1, 1)
        assert await results.get() == "completed"

    run(scenario())


def test_ending_an_observer_sends_close_and_the_last_one_cancels_the_call() -> None:
    async def scenario() -> None:
        kernel = Kernel()
        channel = MultiplexedObservationChannel(kernel.open)

        async def take_one_then_stop() -> None:
            observation = channel.observe_reactor(registration_then_idle(reactor_registration("a")))
            async for _ in observation:
                break
            await observation.aclose()  # type: ignore[attr-defined]

        start(channel, reactor_registration("b"))
        stopping = asyncio.get_running_loop().create_task(take_one_then_stop())
        await settle()
        call = kernel.calls[0]
        call.send(2, 1, Reactor=events("x"))
        await stopping
        await settle()
        assert [(m.StreamId, m.Close) for m in call.messages if m.Close] == [(2, True)]
        assert not call.cancelled

    run(scenario())


def test_the_call_is_cancelled_when_the_last_observer_leaves_and_a_new_one_opens_a_new_call() -> None:
    async def scenario() -> None:
        kernel = Kernel()
        channel = MultiplexedObservationChannel(kernel.open)

        async def observe_once() -> None:
            observation = channel.observe_reactor(registration_then_idle(reactor_registration("a")))
            async for _ in observation:
                break
            await observation.aclose()  # type: ignore[attr-defined]

        task = asyncio.get_running_loop().create_task(observe_once())
        await settle()
        kernel.calls[0].send(1, 1, Reactor=events("x"))
        await task
        assert kernel.calls[0].cancelled
        start(channel, reactor_registration("again"))
        await settle()
        assert len(kernel.calls) == 2

    run(scenario())


def test_a_failed_shared_call_fails_every_stream_and_the_next_observer_gets_a_new_call() -> None:
    async def scenario() -> None:
        kernel = Kernel()
        channel = MultiplexedObservationChannel(kernel.open)
        first = start(channel, reactor_registration("a"))
        second = start(channel, reducer_registration("b"), reducer=True)
        await settle()
        failure = grpc.aio.AioRpcError(grpc.StatusCode.UNAVAILABLE, grpc.aio.Metadata(), grpc.aio.Metadata(), "lost")
        kernel.calls[0].fail(failure)
        assert await first.get() is failure
        assert await second.get() is failure
        start(channel, reactor_registration("a"))
        await settle()
        assert len(kernel.calls) == 2

    run(scenario())


def test_a_slow_observer_does_not_block_another() -> None:
    async def scenario() -> None:
        kernel = Kernel()
        channel = MultiplexedObservationChannel(kernel.open)
        start(channel, reactor_registration("slow"))  # never reads its results
        fast = start(channel, reactor_registration("fast"))
        await settle()
        call = kernel.calls[0]
        for sequence in range(1, 101):
            call.send(1, sequence, Reactor=events(f"slow-{sequence}"))
        call.send(2, 1, Reactor=events("fast-1"))
        received = [(await fast.get()).Partition]
        assert received == ["fast-1"]

    run(scenario())


def test_an_ended_observer_input_sends_close() -> None:
    async def scenario() -> None:
        kernel = Kernel()
        channel = MultiplexedObservationChannel(kernel.open)

        async def finite() -> AsyncIterator[Any]:
            yield reactor_registration("a")

        observation = channel.observe_reactor(finite())
        consumer = asyncio.get_running_loop().create_task(observation.__anext__())
        await settle()
        assert [m.Close for m in kernel.calls[0].messages] == [False, True]
        consumer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await consumer

    run(scenario())
