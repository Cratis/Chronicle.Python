# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

import pytest

from cratis_chronicle.event_sources import (
    ConcurrencyDimensions as D,
)
from cratis_chronicle.event_sources import (
    ConflictingEventSourceRoutingError,
    EventSourceDefinition,
    EventStreamDefinition,
    InvalidEventSourceDefinitionError,
    UnknownEventSourceError,
    UnknownEventStreamError,
    resolve_routing,
    validate_definitions,
)

ACCOUNT = EventSourceDefinition(
    "Account",
    concurrency=D.EVENT_SOURCE_ID,
    streams=(
        EventStreamDefinition("Transactions", concurrency=D.EVENT_SOURCE_ID | D.EVENT_STREAM_ID),
        EventStreamDefinition("Plain"),
    ),
)
OTHER = EventSourceDefinition("Order", streams=(EventStreamDefinition("Lines"),))
DEFS = {d.name: d for d in (ACCOUNT, OTHER)}


def test_wire_flag_values() -> None:
    assert [
        int(f) for f in (D.NONE, D.EVENT_SOURCE_ID, D.EVENT_SOURCE_TYPE, D.EVENT_STREAM_TYPE, D.EVENT_STREAM_ID)
    ] == [0, 1, 2, 4, 8]


def test_duplicate_source_names_rejected() -> None:
    with pytest.raises(InvalidEventSourceDefinitionError):
        validate_definitions([ACCOUNT, ACCOUNT])


def test_duplicate_and_empty_stream_names_rejected() -> None:
    with pytest.raises(InvalidEventSourceDefinitionError):
        EventSourceDefinition("A", streams=(EventStreamDefinition("S"), EventStreamDefinition("S")))
    with pytest.raises(InvalidEventSourceDefinitionError):
        EventSourceDefinition("A", streams=(EventStreamDefinition(" "),))
    with pytest.raises(InvalidEventSourceDefinitionError):
        EventSourceDefinition("")


def test_legacy_append_leaves_source_unset() -> None:
    r = resolve_routing(DEFS, None)
    assert (r.event_source, r.event_stream, r.concurrency) == (None, None, None)


def test_source_default_concurrency() -> None:
    assert resolve_routing(DEFS, "Account").concurrency == D.EVENT_SOURCE_ID


def test_stream_concurrency_wins_over_source() -> None:
    r = resolve_routing(DEFS, "Account", "Transactions")
    assert r.concurrency == D.EVENT_SOURCE_ID | D.EVENT_STREAM_ID


def test_stream_without_dimensions_falls_back_to_source() -> None:
    assert resolve_routing(DEFS, "Account", "Plain").concurrency == D.EVENT_SOURCE_ID


def test_explicit_concurrency_wins_including_none() -> None:
    assert resolve_routing(DEFS, "Account", "Transactions", D.EVENT_STREAM_TYPE).concurrency == D.EVENT_STREAM_TYPE
    assert resolve_routing(DEFS, "Account", explicit_concurrency=D.NONE).concurrency == D.NONE


def test_unknown_source_and_stream() -> None:
    with pytest.raises(UnknownEventSourceError):
        resolve_routing(DEFS, "Nope")
    with pytest.raises(UnknownEventStreamError):
        resolve_routing(DEFS, "Account", "Lines")


def test_stream_without_source_is_rejected() -> None:
    with pytest.raises(ConflictingEventSourceRoutingError):
        resolve_routing(DEFS, None, "Transactions")


def test_per_event_override_wins_and_does_not_inherit_foreign_stream() -> None:
    r = resolve_routing(DEFS, "Order", default_source="Account", default_stream="Transactions")
    assert (r.event_source, r.event_stream, r.concurrency) == ("Order", None, None)
    r = resolve_routing(DEFS, "Order", "Lines", default_source="Account", default_stream="Transactions")
    assert (r.event_source, r.event_stream) == ("Order", "Lines")


def test_call_defaults_apply_when_no_override() -> None:
    r = resolve_routing(DEFS, None, default_source="Account", default_stream="Transactions")
    assert (r.event_source, r.event_stream) == ("Account", "Transactions")
