FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

# Note: build context is the repo root (see docker-compose.yml), so we prefix
# with langgraph-agent/ to reach our own files.
COPY langgraph-agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Run as non-root user
RUN groupadd -r cgcs && useradd -r -g cgcs -d /app -s /sbin/nologin cgcs
COPY langgraph-agent/app/ ./app/
# Bake migrations into the image so the startup runner doesn't depend on the
# host bind-mount (which Coolify Compose deploys don't always wire correctly).
COPY db/migrations /app/db/migrations
RUN chown -R cgcs:cgcs /app
USER cgcs

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
