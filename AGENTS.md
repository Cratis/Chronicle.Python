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

## Local AI work artifacts — `.ai-work/` only

AI-assisted sessions produce working artifacts: plans, handover documents, session notes, continuation prompts, status boards, scratch analyses, research dumps. These are **work records, not documentation**:

- Create every such artifact inside **`.ai-work/`** at the repository root — never at the repository root itself, never under documentation folders, never anywhere else.
- `.ai-work/` is gitignored and must stay untracked. Never commit anything inside it, never `git add -f` anything inside it, and never remove the ignore entry.
- These artifacts must never enter git history or reach GitHub — not on any branch. If you find one tracked in git, move it into `.ai-work/` and remove it from tracking in a dedicated commit.
- A genuine follow-up that must survive the session is **not** a work record — suggest opening a GitHub issue for it (or open one when asked) so future work is tracked where everyone can see it, instead of leaving a planning file behind.
- Knowledge that must outlive the session belongs in the repository's documentation structure through normal review, not in a work record.
