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

## Banner

The banner is not printed on import. Call `pyjetra.botapi.banner.print_banner()` if you want it.

## Disclaimer

pyjetra is not an official Jetra product. You are responsible for your account and for complying with Jetra's terms.

## License

MIT. Author: Ali VEX.
