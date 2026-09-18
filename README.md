# بوت تحويل النص إلى صوت (Telegram + Gemini TTS / Edge TTS)

بوت تيليجرام عربي يحوّل النص إلى صوت. بعد إرسال النص يختار المستخدم **المحرك** (جميناي أو إيدج أو فيش) ثم الجنس ثم السرعة، ويُستخدم المحرك المختار فقط (بدون تبديل صامت). عند فشل المحرك المختار تُعرض رسالة خطأ عربية مع إعادة محاولة واحدة اختيارية لنفس المحرك.

## المتطلبات

- Python 3.11+
- ffmpeg
- poppler-utils (`pdftotext`) لاستخراج نص PDF؛ احتياطي بايثون: `pypdf` / `pdfminer.six`
- في ملف `.env`: `TELEGRAM_BOT_TOKEN` (أو `BOT_TOKEN`) و`GEMINI_API_KEY` (لمحرك Gemini) و`FISH_API_KEY` (لمحرك Fish)
- البوت **خاص**: فقط المعرّفات في `ALLOWED_USER_IDS` (افتراضي `8415608677`)؛ غير المسموح يُرفض بـ «هذا البوت خاص.»

## المحركات والأصوات

| المحرك | أصوات تقريبية |
|--------|----------------|
| Gemini | رجل: `Fenrir` · امرأة: `Aoede` (قابلة للتعديل عبر env) |
| Edge | رجل: `ar-SA-HamedNeural` · امرأة: `ar-SA-ZariyahNeural` |
| Fish | أصوات عربية عامة من مكتبة Fish (قابلة للتعديل عبر `FISH_VOICE_MALE` / `FISH_VOICE_FEMALE`) |

السرعات: بطيء `0.75` · عادي `1.0` · سريع `1.25` · أسرع `1.5`  
(Edge عبر `rate`، وGemini عبر `ffmpeg atempo` بعد التوليد، وFish عبر `prosody.speed`)

نموذج Fish الافتراضي: `FISH_TTS_MODEL=s2.1-pro-free`. استنساخ الصوت عبر الواجهة غير مدعوم بعد (يمكن لاحقاً).

نماذج Gemini الافتراضية: `TTS_MODEL=gemini-2.5-flash-preview-tts` مع احتياطي `TTS_FALLBACK_MODEL=gemini-2.5-pro-preview-tts`.

## التشغيل

```bash
cd /workspace/telegram-tts-bot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
ffmpeg -version   # يجب أن يكون مثبتاً

.venv/bin/python -m tts_bot
# أو للإبقاء على التشغيل:
nohup bash scripts/run_forever.sh >/dev/null 2>&1 &
```

- السجلات: `data/bot.log`
- رقم العملية: `data/bot.pid`

## الاستخدام

1. `/start` — ترحيب وشرح التدفق
2. أرسل أي نص، أو `/tts نصك هنا`، أو أرسل مستند PDF أو ملف نص (`.txt`)
3. اختر المحرك: «جميناي» أو «إيدج» أو «فيش»
4. اختر «رجل» أو «امرأة»
5. اختر السرعة من الأزرار
6. يستلم ملفاً صوتياً واحداً (MP3) بالمحرك المختار. النصوص الطويلة تُقسَّم (~800–1200 حرف) ثم تُدمج بـ ffmpeg

PDF: يظهر «جاري استخراج النص من PDF…» ثم نفس أزرار المحرك. الحد 20 ميغابايت. الملفات الممسوحة (صور فقط) تُرفض برسالة «النص غير قابل للاستخراج» (لا يوجد OCR بعد).

ملف نص (`.txt`): يظهر «جاري قراءة ملف النص…» ثم نفس أزرار المحرك. الترميز: UTF-8 ثم Windows-1256 ثم Latin-1. الحد 20 ميغابايت (`TXT_MAX_BYTES`). الملف الفارغ يُرفض برسالة عربية.

## ملاحظات

- حالة الاختيار معلّقة في الذاكرة وتنتهي صلاحيتها تلقائياً
- نص جديد يستبدل الاختيار المعلّق
- الضغط المكرر على نفس الزر بعد البدء يُتجاهل
- لا تُطبع المفاتيح السرية في السجلات

## النشر على Render (Web Service — وضع Webhook)

الخطة المجانية تنام بعد الخمول؛ أول رسالة بعد الاستيقاظ قد تتأخر (مقبول).

1. ارفع المشروع إلى GitHub ثم في [Render](https://render.com): **New → Web Service** (أو Blueprint عبر `render.yaml`).
2. بيئة التشغيل: **Docker** (يستخدم `Dockerfile` مع `ffmpeg` و`poppler-utils`).
3. **Start Command**: اترك الافتراضي من الـ Dockerfile  
   `python -m tts_bot`  
   (يستمع على `$PORT` تلقائياً).
4. **Health Check Path**: `/health` (أو `/`).
5. أضف متغيرات البيئة (Environment):
   - `TELEGRAM_BOT_TOKEN` (إلزامي)
   - `GEMINI_API_KEY` (لمحرك جميناي)
   - `FISH_API_KEY` (لمحرك فيش)
   - `ALLOWED_USER_IDS` (معرّفات تيليجرام المسموحة، مفصولة بفواصل)
   - `COHERE_API_KEY` / `COHERE_MODEL` (اختياري — وحدة المقالات)
   - `WEBHOOK_SECRET` (اختياري لكن مستحسن — سر التحقق من تيليجرام)
   - `WEBHOOK_PATH=telegram` (اختياري؛ الافتراضي `telegram`)
6. بعد النشر يضبط البوت الـ webhook تلقائياً إلى  
   `https://$RENDER_EXTERNAL_HOSTNAME/telegram`  
   (أو المسار في `WEBHOOK_PATH`). لا حاجة لـ polling على Render.
7. محلياً: بدون `RENDER` / `WEBHOOK_URL` / `RENDER_EXTERNAL_HOSTNAME` يعمل البوت بـ **long polling** كالسابق.

مسارات HTTP:
- `GET /` و `GET /health` → `200 ok`
- `POST /telegram` (وأيضاً `/webhook` كاسم بديل) → تحديثات تيليجرام
