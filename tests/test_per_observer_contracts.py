# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.
"""Pins the per-observer observation and projection registration contracts the client falls back to."""
from cratis_chronicle_contracts import observation_reactors_pb2_grpc, observation_reducers_pb2_grpc, projections_pb2
from cratis_chronicle_contracts import projections_pb2_grpc


class _RecordingChannel:
    def __init__(self) -> None:
        self.streams: list[str] = []
        self.unary: list[str] = []

    def stream_stream(self, method: str, **_: object) -> object:
        self.streams.append(method)
        return object()

    def unary_unary(self, method: str, **_: object) -> object:
        self.unary.append(method)
        return object()


def test_reactors_are_observed_with_one_stream_per_observer() -> None:
    channel = _RecordingChannel()
    observation_reactors_pb2_grpc.ReactorsStub(channel)  # type: ignore[no-untyped-call]
    assert channel.streams == ["/Cratis.Chronicle.Contracts.Observation.Reactors.Reactors/Observe"]


def test_reducers_are_observed_with_one_stream_per_observer() -> None:
    channel = _RecordingChannel()
    observation_reducers_pb2_grpc.ReducersStub(channel)  # type: ignore[no-untyped-call]
    assert channel.streams == ["/Cratis.Chronicle.Contracts.Observation.Reducers.Reducers/Observe"]


def test_projection_registration_is_a_single_unary_call_without_a_registrant() -> None:
    channel = _RecordingChannel()
    projections_pb2_grpc.ProjectionsStub(channel)  # type: ignore[no-untyped-call]
    request = projections_pb2.RegisterRequest(EventStore="store")
    assert "/Cratis.Chronicle.Contracts.Projections.Projections/Register" in channel.unary
    assert request.Registrant == ""
