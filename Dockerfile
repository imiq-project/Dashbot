# --- Builder stage: compile/wheel dependencies into an isolated user site ---
FROM python:3.11-slim AS builder

WORKDIR /app

# System build deps occasionally needed by wheel-less packages (e.g. neo4j,
# sentence-transformers on first run). Keep minimal.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# --- Runtime stage: slim image with only the installed site-packages ---
FROM python:3.11-slim

RUN groupadd -r app && useradd -r -g app -m -d /home/app app

COPY --from=builder --chown=app:app /root/.local /home/app/.local
ENV PATH=/home/app/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

WORKDIR /home/app/dashbot
COPY --chown=app:app . .

EXPOSE 5000

USER app

# Production: 4 workers, uvloop + httptools when available. On platforms where
# uvloop is missing (which should not happen in this Linux image but just in
# case) fall back to the default asyncio loop so the container still boots.
CMD ["sh", "-c", "if python -c 'import uvloop' 2>/dev/null; then exec uvicorn api:app --host 0.0.0.0 --port 5000 --workers 4 --loop uvloop --http httptools; else exec uvicorn api:app --host 0.0.0.0 --port 5000 --workers 4; fi"]
