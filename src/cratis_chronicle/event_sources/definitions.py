# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

"""Registered event source and event stream definitions.

Definitions describe routing and default concurrency for appends. They are deliberately independent of event types.
The values of :class:`ConcurrencyDimensions` mirror the wire enum of the Chronicle `EventSources` service.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import IntFlag


class ConcurrencyDimensions(IntFlag):
    """Dimensions of an append that a concurrency check covers. Matches the wire flags."""

    NONE = 0
    EVENT_SOURCE_ID = 1
    EVENT_SOURCE_TYPE = 2
    EVENT_STREAM_TYPE = 4
    EVENT_STREAM_ID = 8


class InvalidEventSourceDefinitionError(ValueError):
    """Raised when event source or stream definitions are invalid."""


@dataclass(frozen=True)
class EventStreamDefinition:
    """A stable, named stream of an event source."""

    name: str
    description: str = ""
    concurrency: ConcurrencyDimensions = ConcurrencyDimensions.NONE


@dataclass(frozen=True)
class EventSourceDefinition:
    """A stable, named event source with optional default concurrency and streams."""

    name: str
    description: str = ""
    concurrency: ConcurrencyDimensions = ConcurrencyDimensions.NONE
    streams: tuple[EventStreamDefinition, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "streams", tuple(self.streams))
        if not self.name or not self.name.strip():
            raise InvalidEventSourceDefinitionError("An event source must have a non-empty name")
        seen: set[str] = set()
        for stream in self.streams:
            if not stream.name or not stream.name.strip():
                raise InvalidEventSourceDefinitionError(f"Event source '{self.name}' has a stream without a name")
            if stream.name in seen:
                raise InvalidEventSourceDefinitionError(
                    f"Event source '{self.name}' defines stream '{stream.name}' more than once"
                )
            seen.add(stream.name)

    def stream(self, name: str) -> EventStreamDefinition | None:
        """Find a stream by name, or `None` when the source does not define it."""
        return next((stream for stream in self.streams if stream.name == name), None)


def validate_definitions(definitions: Iterable[EventSourceDefinition]) -> tuple[EventSourceDefinition, ...]:
    """Reject duplicate source names. Registering the result is an upsert on the Kernel."""
    result = tuple(definitions)
    seen: set[str] = set()
    for definition in result:
        if definition.name in seen:
            raise InvalidEventSourceDefinitionError(f"Event source '{definition.name}' is defined more than once")
        seen.add(definition.name)
    return result
