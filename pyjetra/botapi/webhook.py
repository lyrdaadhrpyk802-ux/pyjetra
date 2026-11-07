# [EN] Helpers to plug PyJetra into a webhook endpoint.

import json
from typing import Callable, Optional


SECRET_HEADER = "X-Jetra-Bot-Api-Secret-Token"


class WebhookRejected(Exception):
    """Raised when an incoming webhook request is not accepted."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _check_secret(headers: dict, secret_token: Optional[str]) -> None:
    if not secret_token:
        return
    # HTTP header names are case-insensitive; normalize before lookup.
    normalized = {k.lower(): v for k, v in headers.items()}
    got = normalized.get(SECRET_HEADER.lower())
    if got != secret_token:
        raise WebhookRejected("Invalid secret token")


def _dispatch(bot, update: dict) -> None:
    if isinstance(update, dict):
        bot.process_update(update)


def make_wsgi_handler(bot, secret_token: Optional[str] = None,
                      path: str = "/webhook") -> Callable:
    """Build a WSGI callable for Flask/Django/etc.

    Usage with Flask:

        app.add_url_rule(
            "/webhook",
            view_func=make_wsgi_handler(bot, secret_token="..."),
            methods=["POST"],
        )
    """

    def handler(environ, start_response):
        if environ.get("REQUEST_METHOD") != "POST":
            start_response(
                "405 Method Not Allowed",
                [("Content-Type", "text/plain")],
            )
            return [b"Method Not Allowed"]

        headers = {}
        for k, v in environ.items():
            if k.startswith("HTTP_"):
                headers[k[5:].replace("_", "-")] = v

        try:
            _check_secret(headers, secret_token)
        except WebhookRejected:
            start_response("403 Forbidden", [("Content-Type", "text/plain")])
            return [b"Forbidden"]

        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0

        body = environ["wsgi.input"].read(length) if length else b""
        try:
            update = json.loads(body or b"{}")
        except Exception:
            start_response("400 Bad Request", [("Content-Type", "text/plain")])
            return [b"Bad Request"]

        try:
            _dispatch(bot, update)
        except Exception:
            # Never leak internal errors to Jetra; log nothing by default.
            pass

        start_response("200 OK", [("Content-Type", "application/json")])
        return [b'{"ok":true}']

    return handler


def make_asgi_handler(bot, secret_token: Optional[str] = None,
                      path: str = "/webhook") -> Callable:
    """Build an ASGI callable for FastAPI/Starlette.

    Usage with FastAPI:

        app.add_api_route(
            "/webhook",
            make_asgi_handler(bot, secret_token="..."),
            methods=["POST"],
        )
    """

    async def handler(scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") != "POST":
            await send({
                "type": "http.response.start",
                "status": 405,
                "headers": [(b"content-type", b"text/plain")],
            })
            await send({
                "type": "http.response.body",
                "body": b"Method Not Allowed",
            })
            return

        headers = {}
        for raw_name, raw_val in scope.get("headers", []):
            try:
                headers[raw_name.decode()] = raw_val.decode()
            except Exception:
                pass

        try:
            _check_secret(headers, secret_token)
        except WebhookRejected:
            await send({
                "type": "http.response.start",
                "status": 403,
                "headers": [(b"content-type", b"text/plain")],
            })
            await send({"type": "http.response.body", "body": b"Forbidden"})
            return

        body = b""
        while True:
            msg = await receive()
            if msg["type"] != "http.request":
                break
            body += msg.get("body", b"")
            if not msg.get("more_body"):
                break

        try:
            update = json.loads(body or b"{}")
        except Exception:
            await send({
                "type": "http.response.start",
                "status": 400,
                "headers": [(b"content-type", b"text/plain")],
            })
            await send({"type": "http.response.body", "body": b"Bad Request"})
            return

        try:
            _dispatch(bot, update)
        except Exception:
            pass

        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        })
        await send({"type": "http.response.body", "body": b'{"ok":true}'})

    return handler