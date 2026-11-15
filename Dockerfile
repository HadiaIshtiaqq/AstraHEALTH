# ASTRAHEALTH AI: hosted demo image (Render free plan, no local LLM).
# The mission version runs fully offline on a laptop with a local model; see README.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_MODE=hosted_demo \
    LOCAL_LLM_ENABLED=false \
    BACKUPS_ENABLED=false \
    AGENT_TIMEOUT_S=60 \
    LOG_LEVEL=WARNING

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/app backend/app
COPY backend/rules backend/rules
COPY knowledge knowledge
COPY frontend/dist frontend/dist
COPY deploy deploy

WORKDIR /app/backend
# Seed the synthetic demo once at build time so a cold start on a tiny instance is fast.
RUN python ../deploy/prebuild_demo.py \
    && useradd --create-home astra \
    && chown -R astra /app/backend/data /app/knowledge

USER astra
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips '*'"]
