# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

from cratis_chronicle_contracts.events_pb2 import EventType
from cratis_chronicle_contracts.events_pb2_grpc import EventTypesStub
from cratis_chronicle_contracts.protobuf_net.bcl_pb2 import Guid


def test_generated_contract_dependency_is_available() -> None:
    event_type = EventType(Id="example", Generation=1)
    guid = Guid(lo=1, hi=2)

    assert event_type.Id == "example"
    assert event_type.Generation == 1
    assert guid.lo == 1
    assert guid.hi == 2
    assert EventTypesStub is not None
