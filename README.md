# Chronicle for Python

[![Build](https://github.com/Cratis/Chronicle.Python/actions/workflows/build.yml/badge.svg)](https://github.com/Cratis/Chronicle.Python/actions/workflows/build.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

This repository is the experimental Python client for [Cratis Chronicle](https://github.com/Cratis/Chronicle).
It is being established as an idiomatic, async-first layer over Chronicle's generated gRPC contracts.

> [!IMPORTANT]
> The client is in its initial implementation stage. No package has been published, and no compatibility,
> feature-parity, or support commitment is implied.

## Start contributing

The repository currently provides the package structure, quality gates, contribution workflow, and an ordered
client-development guide. The first implementation milestone is a minimal authenticated append against a local
Chronicle kernel.

1. Read [CONTRIBUTING.md](CONTRIBUTING.md).
2. Follow the [client development guide](Documentation/client-development-guide.md).
3. Start with [connection-string parsing](https://github.com/Cratis/Chronicle.Python/issues/2), the current good-first-issue contribution.
4. Submit a pull request from a fork or branch.

## Development setup

Python 3.10 or newer is required.

```shell
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Run the same checks as CI:

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
