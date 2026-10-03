# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

"""Dynamic access to the generated event sequence contracts.

The ``eventsequences_pb2.pyi`` stub in the contracts package declares an enum member named ``None``, which is not valid
Python syntax, so mypy aborts as soon as it parses the stub. Importing the modules dynamically keeps the type check
running; the values are used through the narrow wrappers in ``client.py``. Remove this module when the contracts stub
is valid.
"""

from importlib import import_module
from typing import Any

messages: Any = import_module("cratis_chronicle_contracts.eventsequences_pb2")
services: Any = import_module("cratis_chronicle_contracts.eventsequences_pb2_grpc")
