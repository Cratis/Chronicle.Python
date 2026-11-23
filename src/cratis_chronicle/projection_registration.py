# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.
"""Register projections and wait until the kernel has applied them."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from collections.abc import Awaitable, Callable
from typing import Any, Final

import grpc
from cratis_chronicle_contracts import projections_pb2

logger = logging.getLogger("cratis_chronicle")

#: The longest a client waits for the kernel to apply an accepted registration; the same as the .NET client.
MAX_WAIT_FOR_ACCEPTED_REGISTRATION: Final = 300.0

_INITIAL_POLL_DELAY: Final = 0.05
_MAX_POLL_DELAY: Final = 2.0
_INITIAL_RETRY_DELAY: Final = 0.1
_MAX_RETRY_DELAY: Final = 5.0


class ProjectionRegistrationNotApplied(Exception):
    """The kernel accepted a registration but failed to apply it."""

    def __init__(self, registrant: str, failure: str) -> None:
        super().__init__(f"The kernel could not apply the projections registered by '{registrant}': {failure}")
        self.registrant = registrant
        self.failure = failure


def default_registrant() -> str:
    """Identify this program to the kernel, the way the .NET client uses the entry assembly name.

    The registrant scopes the kernel's registration intent, so every registration made by one program, across
    restarts, must use the same value.
    """
    main = sys.modules.get("__main__")
    name = getattr(getattr(main, "__spec__", None), "name", None) or getattr(main, "__file__", None) or sys.argv[0]
    return os.path.splitext(os.path.basename(str(name)))[0] if name else ""


def _retry_after(error: grpc.aio.AioRpcError) -> float | None:
    for key, value in error.trailing_metadata() or ():
        if key == "retry-after":
            try:
                seconds = float(value if isinstance(value, str) else bytes(value).decode())
            except ValueError:
                return None
            return seconds if seconds >= 0 else None
    return None


async def register_projections(
    stub: Any,
    request: projections_pb2.RegisterRequest,
    *,
    registrant: str | None = None,
    max_wait: float = MAX_WAIT_FOR_ACCEPTED_REGISTRATION,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Register projections, then wait for the kernel to apply them.

    The request carries ``registrant`` (the program identifier by default). A busy kernel answers ``UNAVAILABLE``
    with a ``retry-after`` trailer; the call is retried after that many seconds. Raises
    :class:`ProjectionRegistrationNotApplied` when the kernel reports the registration failed.

    Args:
        stub: A ``ProjectionsStub`` (``grpc.aio``).
        request: The registration to send.
        registrant: Overrides the registrant sent with the request.
        max_wait: Upper bound, in seconds, for retrying and for waiting on the kernel to apply.
        sleep: Awaitable sleep, replaceable in specs.
        clock: Monotonic clock, replaceable in specs.
    """
    request.Registrant = registrant if registrant is not None else (request.Registrant or default_registrant())
    deadline = clock() + max_wait
    delay = _INITIAL_RETRY_DELAY
    while True:
        try:
            await stub.Register(request)
            break
        except grpc.aio.AioRpcError as error:
            if error.code() != grpc.StatusCode.UNAVAILABLE or clock() >= deadline:
                raise
            wait = _retry_after(error)
            await sleep(wait if wait is not None else delay)
            delay = min(delay * 2, _MAX_RETRY_DELAY)
    await wait_for_accepted_registration(
        stub, request.EventStore, request.Registrant, max_wait=max(0.0, deadline - clock()), sleep=sleep, clock=clock
    )


async def wait_for_accepted_registration(
    stub: Any,
    event_store: str,
    registrant: str,
    *,
    max_wait: float = MAX_WAIT_FOR_ACCEPTED_REGISTRATION,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Poll ``GetRegistrationStatus`` until the registration is no longer pending.

    An older kernel answers ``UNIMPLEMENTED`` (it applied the registration before replying), which ends the wait.
    Running out of time logs a warning and returns; the kernel keeps applying the registration.
    """
    deadline = clock() + max_wait
    delay = _INITIAL_POLL_DELAY
    request = projections_pb2.GetRegistrationStatusRequest(EventStore=event_store, Registrant=registrant)
    while True:
        try:
            status = await stub.GetRegistrationStatus(request)
        except grpc.aio.AioRpcError as error:
            if error.code() == grpc.StatusCode.UNIMPLEMENTED:
                return
            raise
        if status.State == projections_pb2.Applied:
            return
        if status.State == projections_pb2.Failed:
            raise ProjectionRegistrationNotApplied(registrant, status.Failure)
        if clock() >= deadline:
            logger.warning(
                "The kernel accepted the projections registered by '%s' but has not finished applying them "
                "after %s seconds; carrying on, the kernel keeps applying them",
                registrant,
                max_wait,
            )
            return
        await sleep(delay)
        delay = min(delay * 2, _MAX_POLL_DELAY)
