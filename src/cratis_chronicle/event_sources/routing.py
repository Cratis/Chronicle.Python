# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

"""Resolution of append routing and concurrency against registered definitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .definitions import ConcurrencyDimensions, EventSourceDefinition


class UnknownEventSourceError(LookupError):
    """Raised when an append names an event source that is not registered."""


class UnknownEventStreamError(LookupError):
    """Raised when an append names a stream the event source does not define."""


class ConflictingEventSourceRoutingError(ValueError):
    """Raised when an explicit stream or source contradicts the definition used for the append."""


@dataclass(frozen=True)
class ResolvedRouting:
    """Routing for one event. `event_source` is `None` for legacy appends (unset, never fabricated)."""

    event_source: str | None
    event_stream: str | None
    concurrency: ConcurrencyDimensions | None


def resolve_routing(
    definitions: Mapping[str, EventSourceDefinition],
    source: str | None,
    stream: str | None = None,
    explicit_concurrency: ConcurrencyDimensions | None = None,
    default_source: str | None = None,
    default_stream: str | None = None,
) -> ResolvedRouting:
    """Resolve routing for a single event.

    A per-event `source`/`stream` wins over the call-level `default_*`. Names must be registered and a stream must
    belong to its source. An `explicit_concurrency` always wins over definition defaults; the stream default wins over
    the source default. Without a source nothing is resolved and a stream is rejected.
    """
    source_name = source if source is not None else default_source
    stream_name = stream if stream is not None else default_stream
    if source_name is None:
        if stream is not None:
            raise ConflictingEventSourceRoutingError(f"Stream '{stream}' was given without an event source")
        return ResolvedRouting(None, None, explicit_concurrency)
    definition = definitions.get(source_name)
    if definition is None:
        raise UnknownEventSourceError(f"Event source '{source_name}' is not registered")
    if source is not None and stream is None and default_stream is not None and source != default_source:
        # A per-event source override must not inherit a stream that belongs to the call-level source.
        stream_name = None
    concurrency = explicit_concurrency
    if stream_name is not None:
        stream_definition = definition.stream(stream_name)
        if stream_definition is None:
            raise UnknownEventStreamError(f"Event source '{source_name}' does not define stream '{stream_name}'")
        if concurrency is None and stream_definition.concurrency != ConcurrencyDimensions.NONE:
            concurrency = stream_definition.concurrency
    if concurrency is None and definition.concurrency != ConcurrencyDimensions.NONE:
        concurrency = definition.concurrency
    return ResolvedRouting(source_name, stream_name, concurrency)
