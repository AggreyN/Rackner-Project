# Rackner FDI backend — same image for local compose and ECS Fargate.
#
# Build:  docker build -t rackner-fdi-backend .
# Run:    docker compose up   (see docker-compose.yml — app + local Postgres)

FROM python:3.12-slim

# Never write .pyc, never buffer stdout (JSON logs must stream to CloudWatch).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Dependencies first so code edits don't bust the pip layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only what the service needs at runtime — tests, venv, data and .env are
# excluded by .dockerignore (the .env exclusion is a security boundary, not an
# optimization: secrets must reach prod via the task definition, never baked
# into an image layer).
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

# Non-root: ECS and CIS benchmarks both expect it, and nothing here needs root.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /srv/data/uploads \
    && chown -R appuser:appuser /srv
USER appuser

EXPOSE 8000

# slim has no curl; probe /health with the stdlib. The ALB target group happens
# to probe the same path, so local and prod agree on what "healthy" means.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
