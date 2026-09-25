# Getting started

Chronicle.Python does not yet expose a usable client API or published package. This page will become the
installation and first-append guide when the
[initial authenticated append milestone](https://github.com/Cratis/Chronicle.Python/issues/4) passes its tests.

## What works today

| You want to… | Status |
| --- | --- |
| `pip install cratis-chronicle` from PyPI | Not possible. No package is published |
| Connect to Chronicle and append events from Python | Not possible through this package yet. It exposes only `__version__` |
| Build the client from source and run its checks | Supported. See [Development setup](../README.md#development-setup) |
| Use Chronicle from another language now | Use the [.NET](https://github.com/Cratis/Chronicle), [TypeScript](https://github.com/Cratis/Chronicle.TypeScript), [Kotlin/Java](https://github.com/Cratis/Chronicle.Kotlin), or [Elixir](https://github.com/Cratis/Chronicle.Elixir) client |

## Contribute

To contribute now, follow [Building the Chronicle Python client](client-development-guide.md) and the repository
[contribution guide](../CONTRIBUTING.md). The development guide shows how to run a local kernel and check the
token and gRPC path before you write client code.
