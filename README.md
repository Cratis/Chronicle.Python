# Chronicle for Python

[![Build](https://github.com/Cratis/Chronicle.Python/actions/workflows/build.yml/badge.svg)](https://github.com/Cratis/Chronicle.Python/actions/workflows/build.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

This repository is the experimental Python client for [Cratis Chronicle](https://github.com/Cratis/Chronicle),
the open-source (MIT) event-sourcing database and processing runtime — an event store for building event-sourced
and CQRS applications. It is being established as an idiomatic, async-first layer over Chronicle's generated gRPC
contracts. Python joins the existing [.NET](https://github.com/Cratis/Chronicle),
[TypeScript](https://github.com/Cratis/Chronicle.TypeScript), [Kotlin/Java](https://github.com/Cratis/Chronicle.Kotlin),
and [Elixir](https://github.com/Cratis/Chronicle.Elixir) Chronicle clients.

> [!IMPORTANT]
> The client is in its initial implementation stage. It has no usable client API yet: the `cratis_chronicle`
> package exposes only `__version__`. Nothing is published to PyPI, and no compatibility, feature-parity, or
> support commitment is implied.

## Current status

| Area | Status |
| --- | --- |
| Client API (connect, authenticate, append) | Not implemented. Tracked by [the first authenticated append milestone](https://github.com/Cratis/Chronicle.Python/issues/4) |
| `cratis-chronicle` on PyPI | Not published. Install from a source checkout |
| Generated contracts (`cratis-chronicle-contracts`) | Not on PyPI. Installed automatically from a SHA-256-pinned wheel attached to the [Chronicle v16.38.2 release](https://github.com/Cratis/Chronicle/releases/tag/v16.38.2) |
| Python versions | 3.10 or newer; CI runs 3.10, 3.11, 3.12, 3.13, and 3.14 |
| Shared Chronicle documentation (language tabs) | Not integrated. Tracked by [Python examples in shared Chronicle documentation](https://github.com/Cratis/Chronicle.Python/issues/5) |

## Start contributing

The repository currently provides the package structure, quality gates, contribution workflow, and an ordered
client-development guide. The first implementation milestone is a minimal authenticated append against a local
Chronicle kernel.

1. Read [CONTRIBUTING.md](CONTRIBUTING.md).
2. Follow the [client development guide](Documentation/client-development-guide.md).
3. Start with [connection-string parsing](https://github.com/Cratis/Chronicle.Python/issues/2), the current good-first-issue contribution.
4. Submit a pull request from a fork or branch.

## Development setup

Python 3.10 or newer is required. The install downloads the contracts wheel from `github.com`, so it needs network
access to GitHub release assets as well as PyPI.

```shell
git clone https://github.com/Cratis/Chronicle.Python.git
cd Chronicle.Python
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Confirm that the package and its generated contracts import:

```shell
python -c "import cratis_chronicle, cratis_chronicle_contracts; print(cratis_chronicle.__version__)"
```

The command prints a development version derived from Git, such as `0.0.1.dev47+g…`. It prints `0.0.0` when the
package metadata cannot be found, which usually means the editable install did not run in the active environment.

Run the same checks as CI (the full list, with expected results, is in [CONTRIBUTING.md](CONTRIBUTING.md#required-checks)):

```shell
ruff format --check .
ruff check .
mypy src
pytest
python -m build
python -m twine check dist/*
```

## Repository map

| Path | Purpose |
| --- | --- |
| `src/cratis_chronicle/` | Idiomatic Python client package |
| `tests/` | Unit and contract-facing tests |
| `Documentation/` | Python-specific setup and contributor guidance |
| `Samples/` | Runnable examples added as client milestones become available |

The non-idiomatic generated protobuf surface is owned and released from the core Chronicle repository. It should
not be copied or manually mirrored here.

## Scope

The first bounded path covers:

1. a TLS gRPC channel to a local kernel;
2. OAuth client-credentials authentication;
3. bearer-token propagation on calls;
4. event-store and namespace setup;
5. registration of one event type and schema; and
6. appending one event with an asserted success response.

Projection, reducer, reactor, subscription, automatic-discovery, and reconnect behavior follows only after this
path has executable evidence.

## License

Chronicle.Python is licensed under the [MIT License](LICENSE).
