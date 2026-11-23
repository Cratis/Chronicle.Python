# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.
import pytest
from cratis_chronicle_contracts import clients_pb2

from cratis_chronicle.kernel_status import KernelStatusMonitor


def keep_alive(status: int) -> clients_pb2.ConnectionKeepAlive:
    return clients_pb2.ConnectionKeepAlive(ConnectionId="c", Status=status)


def test_a_keep_alive_without_status_is_accepting(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO", logger="cratis_chronicle"):
        KernelStatusMonitor().observe(clients_pb2.ConnectionKeepAlive(ConnectionId="c"))
    assert caplog.records == []


def test_leaving_accepting_warns_once_and_returning_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    monitor = KernelStatusMonitor()
    with caplog.at_level("INFO", logger="cratis_chronicle"):
        monitor.observe(keep_alive(clients_pb2.Degraded))
        monitor.observe(keep_alive(clients_pb2.Degraded))
        monitor.observe(keep_alive(clients_pb2.Recovering))
        monitor.observe(keep_alive(clients_pb2.Accepting))
    assert [(r.levelname, r.getMessage()) for r in caplog.records] == [
        ("WARNING", "The kernel is not accepting calls normally: Degraded"),
        ("INFO", "The kernel accepts calls normally again"),
    ]


def test_an_unknown_status_does_not_raise(caplog: pytest.LogCaptureFixture) -> None:
    monitor = KernelStatusMonitor()
    with caplog.at_level("INFO", logger="cratis_chronicle"):
        monitor.observe(keep_alive(99))
    assert monitor.status == 99
    assert "99" in caplog.text
