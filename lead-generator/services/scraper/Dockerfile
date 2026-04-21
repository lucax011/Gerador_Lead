FROM python:3.11-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
    && rm -rf /var/lib/apt/lists/*

COPY services/scraper/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# ── Development stage ────────────────────────────────────────────────────────
FROM base AS development
RUN pip install --no-cache-dir watchdog[watchmedo]

COPY shared/ ./shared/
COPY services/scraper/ ./services/scraper/

CMD ["python", "services/scraper/main.py"]

# ── Production stage ─────────────────────────────────────────────────────────
FROM base AS production

COPY shared/ ./shared/
COPY services/scraper/ ./services/scraper/

CMD ["python", "services/scraper/main.py"]
