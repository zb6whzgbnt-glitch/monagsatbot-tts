# Telegram TTS bot for Render Web Service (webhook mode).
# Python 3.11 + ffmpeg + poppler (PDF text extract).
FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=10000

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    poppler-utils \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY tts_bot ./tts_bot

# Ephemeral writable data dir (pending jobs / sqlite if used)
RUN mkdir -p /app/data && chmod 777 /app/data

EXPOSE 10000

# Binds $PORT (Render injects it). Webhook auto-enabled via RENDER_EXTERNAL_HOSTNAME.
CMD ["python", "-m", "tts_bot"]
