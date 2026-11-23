# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.
"""Surface the load status the kernel reports on every keep-alive."""

from __future__ import annotations

import logging
from typing import Final

from cratis_chronicle_contracts import clients_pb2

logger = logging.getLogger("cratis_chronicle")

_ACCEPTING: Final = clients_pb2.Accepting


class KernelStatusMonitor:
    """Logs when the kernel reports it is busy or recovering, and when it accepts calls normally again.

    Feed every keep-alive to :meth:`observe`. A kernel that reports no status is accepting; a status this client
    does not know is reported by number and never raises.
    """

    def __init__(self) -> None:
        """Start out assuming the kernel is accepting."""
        self._status = _ACCEPTING

    @property
    def status(self) -> int:
        """The last status the kernel reported."""
        return self._status

    def observe(self, keep_alive: clients_pb2.ConnectionKeepAlive) -> None:
        """Record a keep-alive, logging only when the status changes."""
        status = keep_alive.Status
        if status == self._status:
            return
        previous, self._status = self._status, status
        if status == _ACCEPTING:
            logger.info("The kernel accepts calls normally again")
        elif previous == _ACCEPTING:
            logger.warning("The kernel is not accepting calls normally: %s", _name(status))


def _name(status: int) -> str:
    try:
        return str(clients_pb2.KernelStatus.Name(status))
    except ValueError:
        return str(status)
