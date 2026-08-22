# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

"""Experimental Python client for Cratis Chronicle."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("cratis-chronicle")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["__version__"]
