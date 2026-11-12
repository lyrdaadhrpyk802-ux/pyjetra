# Contributing to pyjetra

Thank you for your interest in improving pyjetra. This document describes the conventions every contribution must follow.

## Code style

- All code and comments are written in English.
- Display text (strings shown to end users) may be Persian where appropriate.
- No emojis in code. Use Unicode characters only.
- Every Python file starts with the standard header:

```python
# ============================================
#  <path> - <description>
#  All code and comments are English. No emojis.
# ============================================
```

- Clean, readable code with proper `try/except` blocks.
- Errors are logged with `print(f"[module] error: {e}")`.

## File headers

Each module must declare its path and purpose in the header. The header is the first thing reviewers read; keep it short and accurate.

## Syntax check

Before committing, validate every changed Python file:

```bash
python -c "import ast; ast.parse(open('path/to/file.py').read()); print('OK')"
```

Never commit a file that fails `ast.parse`.

## Secrets

- Never hard-code tokens, API keys, or passwords.
- Use `.env` files and `os.getenv()` for secrets.
- `.env` is gitignored and never committed.

## Workflow

1. Open an issue describing the change you want to make.
2. Fork the repository and create a feature branch.
3. Make your changes in small, reviewable commits.
4. Run `ast.parse` on every changed file.
5. Run the offline test suite: `python -m pytest tests/botapi/`.
6. Open a pull request referencing the issue.

## Commit messages

- English, concise, imperative mood.
- Example: `Add inline keyboard example for callback queries`.
- Reference issues with `Fixes #123` or `Refs #123`.

## Examples and docs

- New examples go under `examples/` in the matching difficulty folder.
- Each example must be self-contained and runnable with `python examples/...`.
- Use Persian and English command names so both audiences can follow.
- Update `examples/README.md` if you add a new folder.

## Releases

- Version bumps happen in `pyproject.toml`, `pyjetra/__init__.py`, `pyjetra/botapi/__init__.py`, `pyjetra/botapi/dev_info.py`, and `pyjetra/userapi/__init__.py`.
- `publish.sh` builds, uploads to PyPI, tags, and pushes.
- Always run `ast.parse` on all files before publishing.

## Reporting issues

- Include the pyjetra version: `python -c "import pyjetra; print(pyjetra.__version__)"`.
- Include the full traceback.
- Do not paste tokens or session files.

## Code of conduct

Be respectful. Be direct. No emojis.
