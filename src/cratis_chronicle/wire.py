# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

"""Conversion between Python values and Chronicle's wire values."""

from __future__ import annotations

import dataclasses
import datetime
import enum
import json
import math
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from cratis_chronicle_contracts.protobuf_net.bcl_pb2 import Guid

__all__ = ["ConceptAs", "from_wire_guid", "serialize_content", "to_wire_guid", "to_wire_timestamp", "to_wire_value"]


@dataclasses.dataclass(frozen=True, slots=True)
class ConceptAs:
    """Base for a strongly typed wrapper around a primitive. It serializes as its primitive ``value``."""

    value: Any


def to_wire_guid(value: uuid.UUID) -> Guid:
    """Convert a UUID to the protobuf-net ``Guid`` message: .NET byte order split into two little-endian halves."""
    raw = value.bytes_le
    return Guid(lo=int.from_bytes(raw[:8], "little"), hi=int.from_bytes(raw[8:], "little"))


def from_wire_guid(value: Guid) -> uuid.UUID:
    """Convert a protobuf-net ``Guid`` message back to a UUID."""
    return uuid.UUID(bytes_le=value.lo.to_bytes(8, "little") + value.hi.to_bytes(8, "little"))


def to_wire_timestamp(value: datetime.datetime) -> str:
    """Convert a timezone-aware datetime to an ISO 8601 string with its UTC offset, as ``DateTimeOffset`` expects."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("A datetime must be timezone-aware to be sent to Chronicle")
    return value.isoformat()


def _to_wire_duration(value: datetime.timedelta) -> str:
    """Convert a timedelta to the .NET constant ``TimeSpan`` form ``[-][d.]hh:mm:ss[.fffffff]``."""
    total_microseconds = (value.days * 86400 + value.seconds) * 1_000_000 + value.microseconds
    sign = "-" if total_microseconds < 0 else ""
    total_microseconds = abs(total_microseconds)
    days, remainder = divmod(total_microseconds, 86_400 * 1_000_000)
    hours, remainder = divmod(remainder, 3_600 * 1_000_000)
    minutes, remainder = divmod(remainder, 60 * 1_000_000)
    seconds, microseconds = divmod(remainder, 1_000_000)
    text = f"{hours:02}:{minutes:02}:{seconds:02}"
    if microseconds:
        text += f".{microseconds * 10:07}"
    return f"{sign}{days}.{text}" if days else f"{sign}{text}"


def to_wire_value(value: Any) -> Any:
    """Convert a value to something ``json.dumps`` accepts, in the forms Chronicle expects.

    UUIDs become canonical strings, datetimes ISO 8601 with offset, dates and times ISO 8601, durations .NET
    ``TimeSpan`` strings, enums and ``ConceptAs`` wrappers their primitive value. Dataclasses and mappings become
    objects with their property names unchanged. Anything else is rejected rather than guessed.
    """
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("NaN and infinity cannot be represented in an event")
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime.datetime):
        return to_wire_timestamp(value)
    if isinstance(value, datetime.date | datetime.time):
        return value.isoformat()
    if isinstance(value, datetime.timedelta):
        return _to_wire_duration(value)
    if isinstance(value, ConceptAs):
        return to_wire_value(value.value)
    if isinstance(value, enum.Enum):
        return to_wire_value(value.value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_wire_value(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("Event property names must be strings")
        return {key: to_wire_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [to_wire_value(item) for item in value]
    raise TypeError(f"A value of type {type(value).__name__} cannot be sent to Chronicle")


def serialize_content(content: Any) -> str:
    """Serialize an event's content as the JSON object Chronicle stores. The content must be an object."""
    wire = to_wire_value(content)
    if not isinstance(wire, dict):
        raise TypeError("Event content must be a mapping or a dataclass")
    return json.dumps(wire, separators=(",", ":"), allow_nan=False)
