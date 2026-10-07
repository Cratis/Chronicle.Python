# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

"""Event type definitions and append results."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

__all__ = ["AppendResult", "EventTypeDefinition"]


@dataclass(frozen=True, slots=True)
class EventTypeDefinition:
    """An event type to register: its identifier, generation and JSON schema.

    The schema must be a non-empty JSON schema object. The kernel validates appended content against it.
    """

    id: str
    schema: Mapping[str, Any]
    generation: int = 1

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("An event type id must not be empty")
        if self.generation < 1:
            raise ValueError("An event type generation must be 1 or greater")
        if not self.schema:
            raise ValueError("An event type needs a non-empty JSON schema")

    def schema_json(self) -> str:
        """The schema serialized for the wire."""
        return json.dumps(self.schema, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True, slots=True)
class AppendResult:
    """The outcome of a successful append."""

    sequence_number: int
    correlation_id: UUID
