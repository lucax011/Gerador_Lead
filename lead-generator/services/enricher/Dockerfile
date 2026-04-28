FROM python:3.11-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
COPY services/enricher/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

FROM base AS development
COPY shared/ ./shared/
COPY services/enricher/ ./services/enricher/
CMD ["python", "services/enricher/main.py"]

FROM base AS production
COPY shared/ ./shared/
COPY services/enricher/ ./services/enricher/
CMD ["python", "services/enricher/main.py"]
