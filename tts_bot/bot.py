from __future__ import annotations

import asyncio
import logging
import re
from io import BytesIO

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import (
    ALLOWED_USER_IDS,
    PDF_LONG_WARN_CHARS,
    PDF_MAX_BYTES,
    PENDING_TTL_SEC,
    SPEED_RATES,
    TELEGRAM_BOT_TOKEN,
    TXT_MAX_BYTES,
)
from .pdf_extract import PdfExtractError, extract_pdf_text
from .pending import PendingStore
from .synth import synthesize_full
from .text_file import extract_txt_text

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("tts_bot")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

PENDING = PendingStore(ttl_sec=PENDING_TTL_SEC)

WELCOME = (
    "مرحباً بك في بوت تحويل النص إلى صوت 🎙️\n\n"
    "كيف يعمل البوت:\n"
    "١) أرسل أي نص عادي، أو استخدم /tts متبوعاً بالنص، أو أرسل ملف PDF أو ملف نص (.txt).\n"
    "٢) اختر المحرك: «جميناي» أو «إيدج» أو «فيش».\n"
    "٣) اختر الجنس: «رجل» أو «امرأة».\n"
    "٤) اختر السرعة: بطيء / عادي / سريع / أسرع.\n"
    "٥) يُحوَّل النص كاملاً إلى ملف صوتي واحد بالمحرك الذي اخترته.\n\n"
    "النصوص الطويلة تُقسَّم داخلياً ثم تُدمج في ملف واحد.\n"
    "ملفات PDF: يُستخرج النص ثم يُكمَل نفس التدفق. الملفات الممسوحة "
    "(صور فقط) غير مدعومة حالياً. الحد الأقصى 20 ميغابايت.\n"
    "ملفات النص (.txt): تُقرأ ثم يُكمَل نفس التدفق. الحد الأقصى 20 ميغابايت.\n\n"
    "الأوامر: /start — /tts — /help"
)

HELP = (
    "أرسل نصاً مباشرة أو ملف PDF أو ملف نص (.txt) أو:\n"
    "/tts نصك هنا\n\n"
    "ثم اختر المحرك (جميناي / إيدج / فيش) ثم الجنس ثم السرعة من الأزرار.\n"
    "ستستلم ملفاً صوتياً واحداً للنص كاملاً بالمحرك المختار.\n"
    "لا يتم التبديل الصامت بين المحركات بعد اختيارك.\n\n"
    "PDF: يُستخرج النص ثم تختار المحرك كالمعتاد.\n"
    "ملف نص (.txt): يُقرأ ثم تختار المحرك كالمعتاد.\n"
    "الملفات الممسوحة (صور فقط) غير مدعومة؛ النص غير قابل للاستخراج.\n"
    "الحد الأقصى لحجم PDF أو .txt: 20 ميغابايت."
)

MSG_CHOOSE_ENGINE = "اختر محرك التحويل:"
MSG_CHOOSE_GENDER = "اختر الجنس للصوت:"
MSG_CHOOSE_SPEED = "اختر سرعة القراءة:"
MSG_CONVERT = "جاري التحويل…"
MSG_MERGE = "جاري دمج المقاطع…"
MSG_RETRY = "تعذر التحويل، إعادة المحاولة…"
MSG_ERR = "تعذر تحويل النص إلى صوت بالمحرك المختار. حاول مرة أخرى بعد قليل."
MSG_EXPIRED = "انتهت صلاحية هذا الطلب. أرسل النص من جديد."
MSG_BUSY = "جاري معالجة طلبك الحالي…"
MSG_TTS_EMPTY = "أرسل نصاً بعد /tts أو أرسل النص مباشرة."
MSG_DONE = "تم ✅"
MSG_PRIVATE = "هذا البوت خاص."
MSG_PDF_EXTRACTING = "جاري استخراج النص من PDF…"
MSG_PDF_NO_TEXT = (
    "النص غير قابل للاستخراج. ملفات PDF الممسوحة ضوئياً (صور فقط) "
    "غير مدعومة حالياً، ولا يتوفر التعرف الضوئي على الحروف (OCR) بعد."
)
MSG_PDF_TOO_LARGE = "حجم ملف PDF كبير جداً. الحد الأقصى 20 ميغابايت."
MSG_PDF_FAIL = "تعذر قراءة ملف PDF. تأكد أنه ملف صالح ثم أعد المحاولة."
MSG_PDF_LONG = "النص المستخرج طويل وسيُقسَّم أثناء التحويل إلى صوت."
MSG_PDF_NOT_PDF = "أرسل ملف PDF أو ملف نص (.txt) فقط."
MSG_TXT_READING = "جاري قراءة ملف النص…"
MSG_TXT_EMPTY = "ملف النص فارغ أو لا يحتوي على نص قابل للقراءة."
MSG_TXT_TOO_LARGE = "حجم ملف النص كبير جداً. الحد الأقصى 20 ميغابايت."
MSG_TXT_FAIL = "تعذر قراءة ملف النص. تأكد أنه ملف صالح ثم أعد المحاولة."

CB_ENGINE = "e"
CB_GENDER = "g"
CB_SPEED = "s"

ENGINE_PERFORMER = {
    "gemini": "Gemini TTS",
    "edge": "Edge TTS",
    "fish": "Fish Audio TTS",
}


def _uid(update: Update) -> int | None:
    user = update.effective_user
    if not user or user.is_bot:
        return None
    return user.id


def _is_allowed(uid: int | None) -> bool:
    if uid is None:
        return False
    if not ALLOWED_USER_IDS:
        return False
    return uid in ALLOWED_USER_IDS


async def _reject_private(update: Update) -> None:
    """Reply with short Arabic refusal; no TTS."""
    query = update.callback_query
    if query:
        try:
            await query.answer(MSG_PRIVATE, show_alert=True)
        except Exception:
            pass
        try:
            if query.message:
                await query.message.reply_text(MSG_PRIVATE)
        except Exception:
            pass
        return
    if update.message:
        try:
            await update.message.reply_text(MSG_PRIVATE)
        except Exception:
            pass


def engine_keyboard(job_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "جميناي", callback_data=f"{CB_ENGINE}:{job_id}:gemini"
                ),
                InlineKeyboardButton(
                    "إيدج", callback_data=f"{CB_ENGINE}:{job_id}:edge"
                ),
                InlineKeyboardButton(
                    "فيش", callback_data=f"{CB_ENGINE}:{job_id}:fish"
                ),
            ]
        ]
    )


def gender_keyboard(job_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "رجل", callback_data=f"{CB_GENDER}:{job_id}:male"
                ),
                InlineKeyboardButton(
                    "امرأة", callback_data=f"{CB_GENDER}:{job_id}:female"
                ),
            ]
        ]
    )


def speed_keyboard(job_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "بطيء 0.75", callback_data=f"{CB_SPEED}:{job_id}:0.75"
                ),
                InlineKeyboardButton(
                    "عادي 1.0", callback_data=f"{CB_SPEED}:{job_id}:1.0"
                ),
            ],
            [
                InlineKeyboardButton(
                    "سريع 1.25", callback_data=f"{CB_SPEED}:{job_id}:1.25"
                ),
                InlineKeyboardButton(
                    "أسرع 1.5", callback_data=f"{CB_SPEED}:{job_id}:1.5"
                ),
            ],
        ]
    )


async def post_init(app: Application) -> None:
    await app.bot.delete_webhook(drop_pending_updates=True)
    await app.bot.set_my_commands(
        [
            BotCommand("start", "بدء البوت والترحيب"),
            BotCommand("help", "شرح الاستخدام"),
            BotCommand("tts", "تحويل نص إلى صوت"),
        ]
    )
    me = await app.bot.get_me()
    log.info("bot ready as @%s", me.username)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    uid = _uid(update)
    if uid is None:
        return
    if not _is_allowed(uid):
        await _reject_private(update)
        return
    await update.message.reply_text(WELCOME)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    uid = _uid(update)
    if uid is None:
        return
    if not _is_allowed(uid):
        await _reject_private(update)
        return
    await update.message.reply_text(HELP)


async def cmd_tts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    uid = _uid(update)
    if uid is None:
        return
    if not _is_allowed(uid):
        await _reject_private(update)
        return
    raw = update.message.text or ""
    body = re.sub(r"^/tts(?:@\w+)?\s*", "", raw, count=1, flags=re.IGNORECASE).strip()
    if not body:
        await update.message.reply_text(MSG_TTS_EMPTY)
        return
    await _offer_engine(update, body)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    uid = _uid(update)
    if uid is None:
        return
    if not _is_allowed(uid):
        await _reject_private(update)
        return
    text = update.message.text.strip()
    if not text or text.startswith("/"):
        return
    await _offer_engine(update, text)


async def _offer_engine(
    update: Update,
    text: str,
    *,
    status_message=None,
    extra: str | None = None,
) -> None:
    assert update.message is not None
    uid = _uid(update)
    if uid is None:
        return
    chat_id = update.effective_chat.id
    job = PENDING.create(uid, chat_id, text)
    body = MSG_CHOOSE_ENGINE
    if extra:
        body = f"{extra}\n\n{MSG_CHOOSE_ENGINE}"
    markup = engine_keyboard(job.job_id)
    if status_message is not None:
        try:
            await status_message.edit_text(body, reply_markup=markup)
            return
        except Exception:
            pass
    await update.message.reply_text(body, reply_markup=markup)



def _is_pdf_document(document) -> bool:
    if document is None:
        return False
    mime = (document.mime_type or "").lower()
    if mime in {"application/pdf", "application/x-pdf"}:
        return True
    name = (document.file_name or "").lower()
    return name.endswith(".pdf")


def _is_txt_document(document) -> bool:
    if document is None:
        return False
    mime = (document.mime_type or "").lower()
    if mime in {"text/plain", "text/txt"}:
        return True
    name = (document.file_name or "").lower()
    return name.endswith(".txt")


async def _edit_or_reply(update: Update, status, msg: str) -> None:
    try:
        if status is not None:
            await status.edit_text(msg)
            return
    except Exception:
        pass
    if update.message:
        await update.message.reply_text(msg)


async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.document:
        return
    uid = _uid(update)
    if uid is None:
        return
    if not _is_allowed(uid):
        await _reject_private(update)
        return

    document = update.message.document
    is_pdf = _is_pdf_document(document)
    is_txt = _is_txt_document(document)
    if not is_pdf and not is_txt:
        await update.message.reply_text(MSG_PDF_NOT_PDF)
        return

    max_bytes = PDF_MAX_BYTES if is_pdf else TXT_MAX_BYTES
    too_large = MSG_PDF_TOO_LARGE if is_pdf else MSG_TXT_TOO_LARGE
    fail_msg = MSG_PDF_FAIL if is_pdf else MSG_TXT_FAIL
    progress = MSG_PDF_EXTRACTING if is_pdf else MSG_TXT_READING
    kind = "pdf" if is_pdf else "txt"

    size = document.file_size or 0
    if size > max_bytes:
        await update.message.reply_text(too_large)
        return

    status = await update.message.reply_text(progress)
    try:
        tg_file = await context.bot.get_file(document.file_id)
        buf = BytesIO()
        await tg_file.download_to_memory(buf)
        data = buf.getvalue()
    except Exception:
        log.exception("%s download failed", kind)
        await _edit_or_reply(update, status, fail_msg)
        return

    if len(data) > max_bytes:
        await _edit_or_reply(update, status, too_large)
        return

    if is_pdf:
        try:
            text = await asyncio.to_thread(extract_pdf_text, data)
        except PdfExtractError:
            log.exception("pdf parse failed")
            await _edit_or_reply(update, status, MSG_PDF_FAIL)
            return
        except Exception:
            log.exception("pdf extract failed")
            await _edit_or_reply(update, status, MSG_PDF_FAIL)
            return
        if not text:
            await _edit_or_reply(update, status, MSG_PDF_NO_TEXT)
            return
    else:
        try:
            text = await asyncio.to_thread(extract_txt_text, data)
        except Exception:
            log.exception("txt extract failed")
            await _edit_or_reply(update, status, MSG_TXT_FAIL)
            return
        if not text:
            await _edit_or_reply(update, status, MSG_TXT_EMPTY)
            return

    extra = MSG_PDF_LONG if len(text) >= PDF_LONG_WARN_CHARS else None
    log.info(
        "%s ok chat=%s bytes=%s chars=%s name=%s",
        kind,
        update.effective_chat.id if update.effective_chat else None,
        len(data),
        len(text),
        (document.file_name or "")[:80],
    )
    await _offer_engine(update, text, status_message=status, extra=extra)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    uid = _uid(update)
    if uid is None:
        await query.answer()
        return
    if not _is_allowed(uid):
        await _reject_private(update)
        return

    parts = query.data.split(":")
    if len(parts) != 3:
        await query.answer()
        return

    kind, job_id, value = parts
    job = PENDING.get(job_id)
    if job is None or job.user_id != uid:
        await query.answer(MSG_EXPIRED, show_alert=True)
        try:
            await query.edit_message_text(MSG_EXPIRED)
        except Exception:
            pass
        return

    if job.handled:
        await query.answer()
        return

    if kind == CB_ENGINE:
        if value not in ("gemini", "edge", "fish"):
            await query.answer()
            return
        job.engine = value
        await query.answer()
        try:
            await query.edit_message_text(
                MSG_CHOOSE_GENDER,
                reply_markup=gender_keyboard(job.job_id),
            )
        except Exception:
            await context.bot.send_message(
                chat_id=job.chat_id,
                text=MSG_CHOOSE_GENDER,
                reply_markup=gender_keyboard(job.job_id),
            )
        return

    if kind == CB_GENDER:
        if value not in ("male", "female"):
            await query.answer()
            return
        if not job.engine:
            await query.answer("اختر المحرك أولاً", show_alert=True)
            return
        job.gender = value
        await query.answer()
        try:
            await query.edit_message_text(
                MSG_CHOOSE_SPEED,
                reply_markup=speed_keyboard(job.job_id),
            )
        except Exception:
            await context.bot.send_message(
                chat_id=job.chat_id,
                text=MSG_CHOOSE_SPEED,
                reply_markup=speed_keyboard(job.job_id),
            )
        return

    if kind == CB_SPEED:
        if value not in SPEED_RATES:
            await query.answer()
            return
        if not job.engine:
            await query.answer("اختر المحرك أولاً", show_alert=True)
            return
        if not job.gender:
            await query.answer("اختر الجنس أولاً", show_alert=True)
            return
        if job.handled:
            await query.answer()
            return
        PENDING.mark_handled(job)
        rate = SPEED_RATES[value]
        engine = job.engine
        gender = job.gender
        text = job.text
        await query.answer()
        try:
            await query.edit_message_text(MSG_CONVERT)
        except Exception:
            pass
        await _run_tts(
            context,
            chat_id=job.chat_id,
            text=text,
            engine=engine,
            gender=gender,
            rate=rate,
            status_message_id=query.message.message_id if query.message else None,
        )
        return

    await query.answer()


async def _run_tts(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    chat_id: int,
    text: str,
    engine: str,
    gender: str,
    rate: str,
    status_message_id: int | None,
) -> None:
    async def on_progress(phase: str) -> None:
        msg = MSG_MERGE if phase == "merge" else MSG_CONVERT
        if status_message_id is None:
            return
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message_id,
                text=msg,
            )
        except Exception:
            pass

    async def _set_status(msg: str) -> None:
        if status_message_id is None:
            return
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message_id,
                text=msg,
            )
        except Exception:
            pass

    try:
        await context.bot.send_chat_action(
            chat_id=chat_id, action=ChatAction.UPLOAD_VOICE
        )
        try:
            result = await synthesize_full(
                text,
                gender,
                rate,
                engine=engine,
                on_progress=on_progress,
            )
        except Exception as first_exc:
            # One retry on the same chosen engine only — never switch engines.
            log.warning(
                "tts first attempt failed engine=%s (%s); retrying once",
                engine,
                str(first_exc)[:200],
            )
            await _set_status(MSG_RETRY)
            result = await synthesize_full(
                text,
                gender,
                rate,
                engine=engine,
                on_progress=on_progress,
            )
        bio = BytesIO(result.audio)
        bio.name = "tts.mp3"
        performer = ENGINE_PERFORMER.get(result.engine, result.engine)
        await context.bot.send_audio(
            chat_id=chat_id,
            audio=bio,
            title="TTS",
            performer=performer,
        )
        if status_message_id is not None:
            try:
                await context.bot.delete_message(
                    chat_id=chat_id, message_id=status_message_id
                )
            except Exception:
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_message_id,
                        text=MSG_DONE,
                    )
                except Exception:
                    pass
        log.info(
            "tts ok chat=%s engine=%s gender=%s rate=%s chars=%s bytes=%s",
            chat_id,
            result.engine,
            gender,
            rate,
            len(text),
            len(result.audio),
        )
    except Exception:
        log.exception("tts failed chat=%s engine=%s", chat_id, engine)
        if status_message_id is not None:
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_message_id,
                    text=MSG_ERR,
                )
                return
            except Exception:
                pass
        await context.bot.send_message(chat_id=chat_id, text=MSG_ERR)


def build_app(*, webhook_mode: bool = False) -> Application:
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN / BOT_TOKEN missing")
    builder = Application.builder().token(TELEGRAM_BOT_TOKEN)
    if webhook_mode:
        # Custom HTTP server feeds update_queue; no built-in Updater.
        builder = builder.updater(None)
    else:
        builder = builder.post_init(post_init)
    app = builder.build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("tts", cmd_tts))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    doc_filter = (
        filters.Document.PDF
        | filters.Document.FileExtension("pdf")
        | filters.Document.FileExtension("txt")
        | filters.Document.MimeType("text/plain")
    )
    app.add_handler(MessageHandler(doc_filter, on_document))
    return app


def main() -> None:
    from .config import webhook_mode_enabled

    if webhook_mode_enabled():
        app = build_app(webhook_mode=True)
        log.info("telegram engine-choice tts bot webhook mode")
        from .webhook_server import run_webhook_server

        run_webhook_server(app)
        return

    app = build_app(webhook_mode=False)
    log.info("telegram engine-choice tts bot polling")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"],
    )


if __name__ == "__main__":
    main()
