# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

"""Event source and stream definitions and routing resolution."""

from .definitions import (
    ConcurrencyDimensions,
    EventSourceDefinition,
    EventStreamDefinition,
    InvalidEventSourceDefinitionError,
    validate_definitions,
)
from .routing import (
    ConflictingEventSourceRoutingError,
    ResolvedRouting,
    UnknownEventSourceError,
    UnknownEventStreamError,
    resolve_routing,
)

__all__ = [
    "ConcurrencyDimensions",
    "ConflictingEventSourceRoutingError",
    "EventSourceDefinition",
    "EventStreamDefinition",
    "InvalidEventSourceDefinitionError",
    "ResolvedRouting",
    "UnknownEventSourceError",
    "UnknownEventStreamError",
    "resolve_routing",
    "validate_definitions",
]
