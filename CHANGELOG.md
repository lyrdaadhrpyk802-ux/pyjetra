# Changelog

## [2.0.2] - 2026-11-07

### Fixed
- botapi, userapi: `__version__` was stuck at the pre-merge value; both now match the package version 2.0.2.
- userapi: `send_poll` rewritten to match the schema: `public_voters` uses the correct flag bit, `option` is length-prefixed TL bytes, quiz mode sends `correct_answers`, and input validation is added (2 to 10 options).
- Verified against the live server by sending a basic poll and a quiz poll to Saved Messages.

### Known limitations
- `send_poll` to group chats is not verified. The test account currently gets CHANNEL_INVALID on group 4782, so group access must be checked first.
- `anonymous=False` (public voters) has not been tested against the live server.
- `remove_password` returns True but does not remove the password. The request structure is known to be wrong and is not fixed in this release.
- `send_reaction` returns REACTION_INVALID for all emojis.
- `create_forum_topic`, `start_bot`, `get_bot_info`, `create_basic_chat`, `get_support`, `get_split_ranges`, `export_contact_token`, `get_saved_contacts`, and `smsjobs.*` are not supported by Jetra.
- `get_recent_locations` returns CHANNEL_PRIVATE on the tested group.
- Most `get_*` methods return raw TL bytes rather than parsed objects.
- Only about 55 of roughly 390 userapi methods were exercised against the live server.

## [2.0.1] - 2026-11-07

### Fixed
- userapi: `_get_channel_input` was defined twice; three call sites used `await` on a sync function (TypeError). Fixed.
- userapi: removed duplicate no-argument `get_users()`. The working version takes `user_ids`.
- userapi: removed basic-group `edit_chat_title` and `edit_chat_photo` variants (Jetra has no basic groups). Channel variants remain.
- userapi: `get_channel_messages` used a wrong InputMessage constructor. Fixed to `inputMessageID`.
- botapi: `get_info()` and the version constant now report the package version.

### Known limitations
- `get_recent_locations` returns CHANNEL_PRIVATE on group chats (server-side, under investigation).
- `remove_password` returns True but does not remove the password (server-side).
- `send_reaction` returns REACTION_INVALID for all emojis.
- `send_poll` returns POLL_OPTION_INVALID.
- `create_forum_topic`, `start_bot`, `get_bot_info`, `create_basic_chat` are not supported by Jetra.
- `get_support`, `get_saved_contacts`, `get_split_ranges`, `export_contact_token`, `smsjobs.*` return NOT_IMPLEMENTED.
- Most `get_*` methods return raw TL bytes rather than parsed objects.
- The userapi client has roughly 390 methods; only about 50 were exercised against the live server.

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
