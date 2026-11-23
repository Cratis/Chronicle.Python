# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.
import asyncio
from collections.abc import Awaitable
from typing import Any, TypeVar

import grpc
import pytest
from cratis_chronicle_contracts import projections_pb2

from cratis_chronicle.projection_registration import (
    ProjectionRegistrationNotApplied,
    default_registrant,
    register_projections,
)

T = TypeVar("T")


def run(awaitable: Awaitable[T]) -> T:
    async def bounded() -> T:
        return await asyncio.wait_for(awaitable, 5)

    return asyncio.run(bounded())


def rpc_error(code: grpc.StatusCode, *trailers: tuple[str, str]) -> grpc.aio.AioRpcError:
    return grpc.aio.AioRpcError(code, grpc.aio.Metadata(), grpc.aio.Metadata(*trailers), code.name)


class FakeProjections:
    def __init__(self, registers: list[Any], statuses: list[Any]) -> None:
        self.registers = registers
        self.statuses = statuses
        self.requests: list[Any] = []
        self.status_requests: list[Any] = []

    async def Register(self, request: Any) -> None:  # noqa: N802
        self.requests.append(projections_pb2.RegisterRequest.FromString(request.SerializeToString()))
        outcome = self.registers.pop(0) if self.registers else None
        if isinstance(outcome, BaseException):
            raise outcome

    async def GetRegistrationStatus(self, request: Any) -> Any:  # noqa: N802
        self.status_requests.append(request)
        outcome = self.statuses.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return projections_pb2.RegistrationStatus(State=outcome[0], Failure=outcome[1] if len(outcome) > 1 else "")


class Sleeper:
    def __init__(self) -> None:
        self.delays: list[float] = []
        self.now = 0.0

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)
        self.now += seconds

    def clock(self) -> float:
        return self.now


def register(stub: FakeProjections, sleeper: Sleeper, **options: Any) -> None:
    run(
        register_projections(
            stub,
            projections_pb2.RegisterRequest(EventStore="store"),
            sleep=sleeper,
            clock=sleeper.clock,
            **options,
        )
    )


def test_a_registrant_is_sent_and_status_is_polled_until_applied() -> None:
    stub = FakeProjections([], [(projections_pb2.Pending,), (projections_pb2.Pending,), (projections_pb2.Applied,)])
    sleeper = Sleeper()
    register(stub, sleeper, registrant="orders")
    assert stub.requests[0].Registrant == "orders"
    assert [r.Registrant for r in stub.status_requests] == ["orders"] * 3
    assert stub.status_requests[0].EventStore == "store"
    assert sleeper.delays == [0.05, 0.1]


def test_the_program_name_is_the_default_registrant() -> None:
    stub = FakeProjections([], [(projections_pb2.Applied,)])
    register(stub, Sleeper())
    assert stub.requests[0].Registrant == default_registrant()
    assert default_registrant() != ""


def test_a_failed_registration_is_an_error() -> None:
    stub = FakeProjections([], [(projections_pb2.Failed, "bad projection")])
    with pytest.raises(ProjectionRegistrationNotApplied, match="bad projection"):
        register(stub, Sleeper(), registrant="orders")


def test_an_older_kernel_without_status_polling_is_not_an_error() -> None:
    stub = FakeProjections([], [rpc_error(grpc.StatusCode.UNIMPLEMENTED)])
    register(stub, Sleeper(), registrant="orders")
    assert len(stub.status_requests) == 1


def test_other_status_errors_are_raised() -> None:
    stub = FakeProjections([], [rpc_error(grpc.StatusCode.INTERNAL)])
    with pytest.raises(grpc.aio.AioRpcError):
        register(stub, Sleeper(), registrant="orders")


def test_a_busy_kernel_with_retry_after_is_retried_after_that_many_seconds() -> None:
    stub = FakeProjections([rpc_error(grpc.StatusCode.UNAVAILABLE, ("retry-after", "7"))], [(projections_pb2.Applied,)])
    sleeper = Sleeper()
    register(stub, sleeper, registrant="orders")
    assert len(stub.requests) == 2
    assert sleeper.delays == [7.0]


def test_unavailable_without_retry_after_backs_off() -> None:
    stub = FakeProjections(
        [rpc_error(grpc.StatusCode.UNAVAILABLE), rpc_error(grpc.StatusCode.UNAVAILABLE)], [(projections_pb2.Applied,)]
    )
    sleeper = Sleeper()
    register(stub, sleeper, registrant="orders")
    assert sleeper.delays == [0.1, 0.2]


def test_other_register_errors_are_not_retried() -> None:
    stub = FakeProjections([rpc_error(grpc.StatusCode.INVALID_ARGUMENT)], [])
    with pytest.raises(grpc.aio.AioRpcError):
        register(stub, Sleeper(), registrant="orders")
    assert len(stub.requests) == 1


def test_waiting_gives_up_with_a_warning_and_does_not_fail(caplog: pytest.LogCaptureFixture) -> None:
    stub = FakeProjections([], [(projections_pb2.Pending,)] * 100)
    with caplog.at_level("WARNING", logger="cratis_chronicle"):
        register(stub, Sleeper(), registrant="orders", max_wait=1.0)
    assert "has not finished applying" in caplog.text
