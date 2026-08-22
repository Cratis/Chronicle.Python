# Chronicle.Python repository instructions

This is a Cratis framework repository containing an experimental Python client for Chronicle.

## Boundaries

- The idiomatic Python API lives under `src/cratis_chronicle`.
- Generated protobuf contracts are owned by the core `Cratis/Chronicle` repository and consumed as a package.
- Do not copy generated files into this repository or manually mirror protobuf messages.
- Do not infer feature parity, compatibility, maturity, or support from another Chronicle client.
- Public API design requires maintainer review before broad implementation.

## Engineering rules

- Use Python 3.10-compatible syntax.
- Network APIs are async-first.
- Use American English.
- Add type annotations and keep `mypy` strict mode passing.
- Keep `ruff format`, `ruff check`, `pytest`, package build, and `twine check` passing.
- Add tests for behavior and failure paths; a stub that silently succeeds is a bug.
- Never commit credentials, tokens, customer data, private conversations, transcripts, or generated local artifacts.
- Prefer narrow, reviewable changes and explicit unsupported outcomes.

## Before completion

Run:

```shell
ruff format --check .
ruff check .
mypy src
pytest
rm -rf dist
python -m build
python -m twine check dist/*
```
