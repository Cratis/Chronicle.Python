# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

import dataclasses
import datetime
import enum
import json
import uuid

import pytest

from cratis_chronicle import ConceptAs
from cratis_chronicle.wire import from_wire_guid, serialize_content, to_wire_guid, to_wire_value


def test_guid_round_trips_in_dotnet_byte_order() -> None:
    value = uuid.UUID("00112233-4455-6677-8899-aabbccddeeff")

    wire = to_wire_guid(value)

    assert wire.lo == int.from_bytes(bytes.fromhex("3322110055447766"), "little")
    assert wire.hi == int.from_bytes(bytes.fromhex("8899aabbccddeeff"), "little")
    assert from_wire_guid(wire) == value


def test_random_guids_round_trip() -> None:
    for _ in range(50):
        value = uuid.uuid4()
        assert from_wire_guid(to_wire_guid(value)) == value


class Color(enum.Enum):
    RED = "red"


class Id(ConceptAs):
    pass


@dataclasses.dataclass
class Address:
    city: str


@dataclasses.dataclass
class Person:
    id: uuid.UUID
    ident: Id
    when: datetime.datetime
    born: datetime.date
    at: datetime.time
    took: datetime.timedelta
    color: Color
    address: Address
    tags: list[str]
    nickname: str | None = None


def test_values_are_converted_to_chronicle_forms_with_property_names_untouched() -> None:
    person = Person(
        id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        ident=Id("abc"),
        when=datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.timezone(datetime.timedelta(hours=2))),
        born=datetime.date(1990, 5, 6),
        at=datetime.time(7, 8, 9),
        took=datetime.timedelta(days=1, hours=2, minutes=3, seconds=4, microseconds=500000),
        color=Color.RED,
        address=Address("Oslo"),
        tags=["a", "b"],
    )

    assert json.loads(serialize_content(person)) == {
        "id": "12345678-1234-5678-1234-567812345678",
        "ident": "abc",
        "when": "2026-01-02T03:04:05+02:00",
        "born": "1990-05-06",
        "at": "07:08:09",
        "took": "1.02:03:04.5000000",
        "color": "red",
        "address": {"city": "Oslo"},
        "tags": ["a", "b"],
        "nickname": None,
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (datetime.timedelta(0), "00:00:00"),
        (datetime.timedelta(seconds=90), "00:01:30"),
        (datetime.timedelta(days=3), "3.00:00:00"),
        (datetime.timedelta(seconds=-90), "-00:01:30"),
        (datetime.timedelta(microseconds=1), "00:00:00.0000010"),
    ],
)
def test_durations_use_the_dotnet_constant_form(value: datetime.timedelta, expected: str) -> None:
    assert to_wire_value(value) == expected


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        to_wire_value(datetime.datetime(2026, 1, 1))


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_non_finite_floats_are_rejected(value: float) -> None:
    with pytest.raises(ValueError):
        to_wire_value(value)


def test_unsupported_types_and_non_object_content_are_rejected() -> None:
    with pytest.raises(TypeError):
        to_wire_value(object())
    with pytest.raises(TypeError):
        to_wire_value({1: "a"})
    with pytest.raises(TypeError):
        to_wire_value(b"bytes")
    with pytest.raises(TypeError, match="mapping or a dataclass"):
        serialize_content([1, 2])
