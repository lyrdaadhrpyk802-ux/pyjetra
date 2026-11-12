# pyjetra

Python toolkit for Jetra Messenger, with two independent clients:

- `pyjetra.botapi`: Bot API wrapper (sync and async), with FSM, filters, inline keyboards and webhooks.
- `pyjetra.userapi`: User account client (MTProto-style protocol, SRP login, 2FA).

## Install

```bash
pip install pyjetra[bot]     # Bot API only
pip install pyjetra[user]    # User account only
pip install pyjetra[all]     # both
```

Requires Python 3.10 or newer.

## Bot API quick start

```python
from pyjetra.botapi import JetraBot, CommandFilter

bot = JetraBot("YOUR_BOT_TOKEN")

@bot.on_message(filters=[CommandFilter("start")])
def start(msg):
    msg.reply("Hello from pyjetra")

bot.poll()
```

## User account quick start

```python
from pyjetra.userapi import JetraClient
```

Session and local database files are stored in `~/.pyjetra` by default. Change the location with the `PYJETRA_DATA_DIR` environment variable. Session files are never part of the package.

## Examples

The `examples/` folder contains runnable scripts that teach pyjetra step by step.

| Folder | Topic |
|--------|-------|
| `examples/01_bot_basics/` | Echo bot, Persian+English commands |
| `examples/02_bot_intermediate/` | FSM, inline buttons, webhook |
| `examples/03_bot_advanced/` | Media upload, chat admin, error handling |
| `examples/04_user_basics/` | Login, send message, listen |
| `examples/05_user_intermediate/` | Dialogs, participants, media |
| `examples/06_user_advanced/` | Channel admin, invites, privacy, 2FA, stories |
| `examples/99_recipes/` | Autoresponder, group guard, scheduled sender |

See `examples/README.md` for run instructions and `docs/CONCEPTS.md` for the underlying concepts (TL, access_hash, FSM, session).

Quick run:

```bash
export JETRA_BOT_TOKEN="your_bot_token"
python examples/01_bot_basics/01_echo_bot.py
```

## Helper scripts

`scripts/` contains login helpers and one-off fixers:

- `scripts/login.py` - Interactive login (phone, code, 2FA).
- `scripts/jetra_login.py` - Alternative login flow.
- `scripts/jetra_fix_uid.py` - Repair an old session by reattaching user_id.

Run with `python scripts/login.py` from the project root.

## Banner

The banner is not printed on import. Call `pyjetra.botapi.banner.print_banner()` if you want it.

## Disclaimer

pyjetra is not an official Jetra product. You are responsible for your account and for complying with Jetra's terms.

## License

MIT. Author: Ali VEX.
