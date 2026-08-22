# Contributing to Chronicle.Python

Thank you for helping build the Python client for Chronicle.

## Before starting

- Read the [client development guide](Documentation/client-development-guide.md).
- Discuss public API choices in an issue before implementing a broad surface.
- Keep changes bounded to one observable client milestone.
- Do not copy generated protobuf files or hand-maintain wire contracts in this repository.
- Do not claim compatibility, parity, maturity, security, performance, or support without corresponding evidence
  and maintainer approval.

## Local setup

```shell
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`.

## Required checks

```shell
ruff format --check .
ruff check .
mypy src
pytest
rm -rf dist
python -m build
python -m twine check dist/*
```

All checks must pass before review. New behavior requires tests, including failure behavior where applicable.

## API principles

- Prefer an async-first API for network operations.
- Use idiomatic Python names and types rather than exposing generated protobuf naming as the primary API.
- Provide safe defaults while keeping connection, authentication, serialization, and lifecycle behavior explicit.
- Keep generated contracts behind an internal boundary unless a low-level escape hatch is deliberately accepted.
- Make unsupported behavior visible; never silently succeed with a stub.
- Preserve Chronicle's wire-value contract described in the core repository.

## Pull requests

- Use a focused branch and a concise imperative commit message.
- Complete the pull request template and remove empty sections.
- Add exactly one of `major`, `minor`, or `patch` when the change is release-bearing; use `no-release` for changes
  that intentionally produce no package release.
- Never include credentials, access tokens, customer data, private conversations, or agent transcripts.
- Maintainers may request changes to API shape before accepting an implementation, even when the code works.

## Reporting security concerns

Do not open a public issue for a suspected vulnerability. Follow [SECURITY.md](SECURITY.md).
