# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

from importlib.metadata import version

from cratis_chronicle_contracts.protobuf_net.bcl_pb2 import Guid
from cratis_chronicle_contracts.sequences_pb2 import AppendRequest, EventType
from cratis_chronicle_contracts.sequences_pb2_grpc import EventSequencesStub

from cratis_chronicle import _event_type_contracts as event_types


def test_generated_contract_dependency_is_the_pinned_release() -> None:
    assert version("cratis-chronicle-contracts") == "19.31.3"


def test_generated_contract_dependency_is_available() -> None:
    event_type = EventType(Id="example", Generation=1)
    guid = Guid(lo=1, hi=2)

    assert event_type.Id == "example"
    assert event_type.Generation == 1
    assert guid.lo == 1
    assert guid.hi == 2
    assert AppendRequest(EventType=event_type).EventType.Id == "example"
    assert EventSequencesStub is not None
    assert event_types.services.EventTypesStub is not None
    assert event_types.messages.RegisterEventTypesRequest is not None
