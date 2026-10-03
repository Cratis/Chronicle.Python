# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

import asyncio
import gc
import json
import warnings
from collections.abc import Mapping
from typing import Any

import pytest

from cratis_chronicle import (
    ChronicleConnectionOptions,
    HttpResponse,
    OAuthTokenProvider,
    TokenAuthorizationError,
    TokenRequestError,
    TokenResponseError,
)
from cratis_chronicle.token_provider import DEFAULT_TOKEN_LIFETIME_SECONDS

SECRET = "s3cr3t-value"  # noqa: S105
OPTIONS = ChronicleConnectionOptions(host="kernel.example", client_id="the-client", client_secret=SECRET, port=35001)


def ok(token: str = "tok-1", **extra: Any) -> HttpResponse:
    return HttpResponse(200, json.dumps({"access_token": token, "token_type": "Bearer", **extra}).encode())


class FakeTransport:
    def __init__(self, *responses: HttpResponse | BaseException) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, Mapping[str, str]]] = []
        self.gate: asyncio.Event | None = None

    async def post_form(self, url: str, fields: Mapping[str, str]) -> HttpResponse:
        self.calls.append((url, dict(fields)))
        if self.gate is not None:
            await self.gate.wait()
        response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(response, BaseException):
            raise response
        return response


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def provider(transport: FakeTransport, clock: Clock | None = None) -> OAuthTokenProvider:
    return OAuthTokenProvider(OPTIONS, transport, clock=clock or Clock())


def test_requests_the_token_with_the_client_credentials_form() -> None:
    transport = FakeTransport(ok(expires_in=3600))

    token = asyncio.run(provider(transport).get_token())

    assert token == "tok-1"
    assert transport.calls == [
        (
            "https://kernel.example:35001/connect/token",
            {"grant_type": "client_credentials", "client_id": "the-client", "client_secret": SECRET},
        )
    ]


def test_uses_http_when_tls_is_off_and_brackets_ipv6() -> None:
    options = ChronicleConnectionOptions(host="::1", client_id="a", client_secret="b", tls=False)
    transport = FakeTransport(ok())

    asyncio.run(OAuthTokenProvider(options, transport).get_token())

    assert transport.calls[0][0] == "http://[::1]:35000/connect/token"


def test_caches_the_token_until_shortly_before_it_expires() -> None:
    clock, transport = Clock(), FakeTransport(ok("a", expires_in=100), ok("b", expires_in=100))
    tokens = provider(transport, clock)

    async def scenario() -> list[str]:
        seen = [await tokens.get_token()]
        clock.now += 69  # lifetime 100 -> refresh margin 30 -> still valid at 70
        seen.append(await tokens.get_token())
        clock.now += 2  # past refresh point
        seen.append(await tokens.get_token())
        return seen

    assert asyncio.run(scenario()) == ["a", "a", "b"]
    assert len(transport.calls) == 2


def test_an_absent_expiry_is_cached_only_for_a_short_conservative_time() -> None:
    clock, transport = Clock(), FakeTransport(ok("a"), ok("b"))
    tokens = provider(transport, clock)

    async def scenario() -> list[str]:
        seen = [await tokens.get_token()]
        clock.now += DEFAULT_TOKEN_LIFETIME_SECONDS / 2 - 1
        seen.append(await tokens.get_token())
        clock.now += 2
        seen.append(await tokens.get_token())
        return seen

    assert asyncio.run(scenario()) == ["a", "a", "b"]


def test_short_lifetimes_refresh_at_half_their_life() -> None:
    clock, transport = Clock(), FakeTransport(ok("a", expires_in=10), ok("b", expires_in=10))
    tokens = provider(transport, clock)

    async def scenario() -> list[str]:
        first = await tokens.get_token()
        clock.now += 6
        return [first, await tokens.get_token()]

    assert asyncio.run(scenario()) == ["a", "b"]


def test_concurrent_callers_share_one_request() -> None:
    transport = FakeTransport(ok(expires_in=3600))
    tokens = provider(transport)

    async def scenario() -> list[str]:
        transport.gate = asyncio.Event()
        callers = [asyncio.ensure_future(tokens.get_token()) for _ in range(10)]
        await asyncio.sleep(0.01)
        transport.gate.set()
        return await asyncio.gather(*callers)

    assert asyncio.run(scenario()) == ["tok-1"] * 10
    assert len(transport.calls) == 1


def test_cancelling_one_caller_does_not_cancel_the_shared_request() -> None:
    transport = FakeTransport(ok(expires_in=3600))
    tokens = provider(transport)

    async def scenario() -> str:
        transport.gate = asyncio.Event()
        cancelled = asyncio.ensure_future(tokens.get_token())
        survivor = asyncio.ensure_future(tokens.get_token())
        await asyncio.sleep(0.01)
        cancelled.cancel()
        transport.gate.set()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        return await survivor

    assert asyncio.run(scenario()) == "tok-1"
    assert len(transport.calls) == 1


def test_closing_cancels_the_in_flight_request() -> None:
    transport = FakeTransport(ok(expires_in=3600))
    tokens = provider(transport)

    async def scenario() -> str:
        transport.gate = asyncio.Event()
        caller = asyncio.ensure_future(tokens.get_token())
        await asyncio.sleep(0.01)
        await tokens.aclose()
        with pytest.raises(asyncio.CancelledError):
            await caller
        return "closed"

    assert asyncio.run(scenario()) == "closed"


def test_close_is_idempotent_and_stops_further_use() -> None:
    tokens = provider(FakeTransport(ok()))

    async def scenario() -> None:
        await tokens.aclose()
        await tokens.aclose()
        with pytest.raises(TokenRequestError):
            await tokens.get_token()

    asyncio.run(scenario())


def test_invalidate_forces_a_new_request() -> None:
    transport = FakeTransport(ok("a", expires_in=3600), ok("b", expires_in=3600))
    tokens = provider(transport)

    async def scenario() -> list[str]:
        first = await tokens.get_token()
        tokens.invalidate()
        return [first, await tokens.get_token()]

    assert asyncio.run(scenario()) == ["a", "b"]


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[]",
        b"{}",
        b'{"access_token": ""}',
        b'{"access_token": 5}',
        b'{"access_token": "t", "token_type": "mac"}',
        b'{"access_token": "t", "expires_in": "soon"}',
        b'{"access_token": "t", "expires_in": 0}',
        b'{"access_token": "t", "expires_in": -5}',
        b'{"access_token": "t", "expires_in": true}',
    ],
)
def test_malformed_responses_are_rejected(body: bytes) -> None:
    tokens = provider(FakeTransport(HttpResponse(200, body)))

    with pytest.raises(TokenResponseError):
        asyncio.run(tokens.get_token())


def test_a_null_expires_in_is_treated_as_absent() -> None:
    tokens = provider(FakeTransport(HttpResponse(200, b'{"access_token": "t", "expires_in": null}')))

    assert asyncio.run(tokens.get_token()) == "t"


def test_authorization_failure_is_parsed_and_typed() -> None:
    body = json.dumps({"error": "invalid_client", "error_description": "bad client"}).encode()
    tokens = provider(FakeTransport(HttpResponse(401, body)))

    with pytest.raises(TokenAuthorizationError) as raised:
        asyncio.run(tokens.get_token())

    assert raised.value.status == 401
    assert raised.value.error == "invalid_client"
    assert raised.value.description == "bad client"
    assert "invalid_client" in str(raised.value)


def test_a_failed_request_is_not_cached() -> None:
    transport = FakeTransport(HttpResponse(401, b"{}"), ok())
    tokens = provider(transport)

    async def scenario() -> str:
        with pytest.raises(TokenAuthorizationError):
            await tokens.get_token()
        return await tokens.get_token()

    assert asyncio.run(scenario()) == "tok-1"


def test_an_unexpected_status_is_a_request_error_with_the_status() -> None:
    tokens = provider(FakeTransport(HttpResponse(503, b"down")))

    with pytest.raises(TokenRequestError) as raised:
        asyncio.run(tokens.get_token())

    assert raised.value.status == 503


def test_secrets_never_leak_into_repr_or_errors() -> None:
    echoing = json.dumps({"error": "invalid_client", "error_description": f"wrong {SECRET}"}).encode()
    tokens = provider(FakeTransport(HttpResponse(401, echoing)))

    with pytest.raises(TokenAuthorizationError) as raised:
        asyncio.run(tokens.get_token())

    assert SECRET not in repr(tokens)
    assert SECRET not in str(tokens)
    assert SECRET not in str(raised.value)
    assert SECRET not in repr(raised.value.description)
    assert "****" in str(raised.value)


def test_the_access_token_never_appears_in_repr_or_response_errors() -> None:
    tokens = provider(FakeTransport(ok("super-token", expires_in=3600)))
    asyncio.run(tokens.get_token())

    assert "super-token" not in repr(tokens)
    assert "super-token" not in str(tokens)


def test_invalidating_during_a_refresh_does_not_cache_the_stale_token() -> None:
    transport = FakeTransport(ok("stale", expires_in=3600), ok("fresh", expires_in=3600))
    tokens = provider(transport)

    async def scenario() -> list[str]:
        transport.gate = asyncio.Event()
        in_flight = asyncio.ensure_future(tokens.get_token())
        await asyncio.sleep(0.01)
        tokens.invalidate()
        transport.gate.set()
        waiter = await in_flight
        transport.gate = None
        return [waiter, await tokens.get_token(), await tokens.get_token()]

    assert asyncio.run(scenario()) == ["stale", "fresh", "fresh"]
    assert len(transport.calls) == 2


def test_a_caller_after_invalidation_does_not_join_the_stale_refresh() -> None:
    transport = FakeTransport(ok("stale", expires_in=3600), ok("fresh", expires_in=3600))
    tokens = provider(transport)

    async def scenario() -> str:
        transport.gate = asyncio.Event()
        stale = asyncio.ensure_future(tokens.get_token())
        await asyncio.sleep(0.01)
        tokens.invalidate()
        later = asyncio.ensure_future(tokens.get_token())
        await asyncio.sleep(0.01)
        transport.gate.set()
        await stale
        return await later

    assert asyncio.run(scenario()) == "fresh"


def test_a_failed_shared_refresh_whose_waiters_all_cancelled_leaves_no_unretrieved_exception() -> None:
    transport = FakeTransport(TokenRequestError("unreachable"))
    tokens = provider(transport)
    unhandled: list[dict[str, Any]] = []

    async def scenario() -> None:
        asyncio.get_running_loop().set_exception_handler(lambda _, context: unhandled.append(context))
        transport.gate = asyncio.Event()
        first = asyncio.ensure_future(tokens.get_token())
        second = asyncio.ensure_future(tokens.get_token())
        await asyncio.sleep(0.01)
        first.cancel()
        second.cancel()
        await asyncio.gather(first, second, return_exceptions=True)
        transport.gate.set()
        await asyncio.sleep(0.01)
        gc.collect()
        await asyncio.sleep(0)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        asyncio.run(scenario())
        gc.collect()

    assert unhandled == []
    assert len(transport.calls) == 1


def test_closing_after_invalidation_still_cancels_the_detached_refresh() -> None:
    transport = FakeTransport(ok(expires_in=3600))
    tokens = provider(transport)

    async def scenario() -> None:
        transport.gate = asyncio.Event()
        caller = asyncio.ensure_future(tokens.get_token())
        await asyncio.sleep(0.01)
        tokens.invalidate()
        await tokens.aclose()
        with pytest.raises(asyncio.CancelledError):
            await caller

    asyncio.run(scenario())
