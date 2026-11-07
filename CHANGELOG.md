# Changelog

## [2.0.0] - 2026-11-07

### Changed
- Merged `pyjetra` (Bot API) and `jetrauserapi` (User Account API) into one package.
  - `pyjetra.botapi`: former `pyjetra` package.
  - `pyjetra.userapi`: former `jetrauserapi` package.
  - Imports must be updated: `from pyjetra import JetraBot` becomes `from pyjetra.botapi import JetraBot`; `from jetrauserapi import ...` becomes `from pyjetra.userapi import ...`.
- Minimum Python version raised to 3.10 (Bot API previously supported 3.7+).
- Dependencies are now optional extras: `bot`, `user`, `all`.
- Session and local database default to `~/.pyjetra`, configurable with `PYJETRA_DATA_DIR`. Previously the data directory was inside the package.

### Removed
- Banner is no longer printed on import. Call `print_banner()` explicitly.

### Notes
- The old `jetrauserapi` package on PyPI is superseded by `pyjetra.userapi`.
