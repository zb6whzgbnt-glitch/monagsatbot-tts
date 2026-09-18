"""HTTP health + Telegram webhook server for Render (and similar hosts).

Uses aiohttp so we can expose GET / and GET /health alongside POST /telegram
(or WEBHOOK_PATH). Feeds updates into python-telegram-bot Application.update_queue.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from http import HTTPStatus

from aiohttp import web
from telegram import BotCommand, Update
from telegram.ext import Application

from .config import TELEGRAM_BOT_TOKEN, WEBHOOK_PATH, WEBHOOK_SECRET, WEBHOOK_URL

log = logging.getLogger("tts_bot.webhook")

ALLOWED_UPDATES = ["message", "callback_query"]


def resolve_webhook_url() -> tuple[str, str]:
    """Return (full_webhook_url, url_path_without_leading_slash)."""
    path = (WEBHOOK_PATH or "telegram").strip().strip("/") or "telegram"
    explicit = (WEBHOOK_URL or "").strip().rstrip("/")
    if explicit:
        # If WEBHOOK_URL already ends with the path, use as-is; else append path.
        if explicit.endswith(f"/{path}"):
            return explicit, path
        return f"{explicit}/{path}", path
    host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
    if not host:
        raise SystemExit(
            "Webhook mode needs WEBHOOK_URL or RENDER_EXTERNAL_HOSTNAME"
        )
    return f"https://{host}/{path}", path


def listen_port() -> int:
    return int(os.environ.get("PORT", "8080"))


async def _set_bot_commands(app: Application) -> None:
    await app.bot.set_my_commands(
        [
            BotCommand("start", "بدء البوت والترحيب"),
            BotCommand("help", "شرح الاستخدام"),
            BotCommand("tts", "تحويل نص إلى صوت"),
        ]
    )


async def _run(application: Application) -> None:
    webhook_url, path = resolve_webhook_url()
    port = listen_port()
    secret = (WEBHOOK_SECRET or "").strip() or None

    async def health(_: web.Request) -> web.Response:
        return web.Response(text="ok", content_type="text/plain")

    async def telegram_webhook(request: web.Request) -> web.Response:
        if secret:
            header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if header != secret:
                return web.Response(status=HTTPStatus.FORBIDDEN, text="forbidden")
        try:
            data = await request.json()
        except Exception:
            return web.Response(status=HTTPStatus.BAD_REQUEST, text="bad json")
        update = Update.de_json(data=data, bot=application.bot)
        if update is None:
            return web.Response(status=HTTPStatus.BAD_REQUEST, text="bad update")
        await application.update_queue.put(update)
        return web.Response(text="OK")

    web_app = web.Application()
    web_app.router.add_get("/", health)
    web_app.router.add_get("/health", health)
    web_app.router.add_post(f"/{path}", telegram_webhook)
    # Convenience alias only for the default path name
    if path == "telegram":
        web_app.router.add_post("/webhook", telegram_webhook)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    async with application:
        await application.start()
        await application.bot.set_webhook(
            url=webhook_url,
            secret_token=secret,
            allowed_updates=ALLOWED_UPDATES,
            drop_pending_updates=True,
        )
        await _set_bot_commands(application)
        me = await application.bot.get_me()
        log.info(
            "webhook ready bot=@%s path=/%s port=%s",
            me.username,
            path,
            port,
        )

        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        log.info("http listening on 0.0.0.0:%s (health /, /health)", port)

        await stop.wait()

        log.info("shutting down webhook server")
        await runner.cleanup()
        await application.stop()


def run_webhook_server(application: Application) -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN / BOT_TOKEN missing")
    asyncio.run(_run(application))
