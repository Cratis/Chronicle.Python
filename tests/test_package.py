# Copyright (c) Cratis. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for full license information.

import cratis_chronicle


def test_package_exposes_a_version() -> None:
    assert cratis_chronicle.__version__
