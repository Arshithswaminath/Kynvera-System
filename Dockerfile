# Multi-stage Dockerfile: build wheels in builder stage, install from wheels in final image

# Stage 1: builder - build wheels
FROM python:3.10-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /wheels

# NOTE: repo contains requirements-prods.txt (plural) — use that file so COPY succeeds.
COPY requirements-prods.txt /wheels/requirements-prods.txt

RUN python -m pip install --upgrade pip "setuptools<81" wheel \
 && pip wheel --wheel-dir=/wheels -r /wheels/requirements-prods.txt

# Stage 2: runtime image
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

# Copy built wheels and install from them
COPY --from=builder /wheels /wheels
COPY requirements-prods.txt /app/requirements-prods.txt

RUN python -m pip install --upgrade pip "setuptools<81" wheel \
 && pip install --no-index --find-links=/wheels -r /app/requirements-prods.txt \
 && python -c "import pkg_resources, gunicorn; print('runtime deps OK')"

# Copy application code
COPY . /app

# Create non-root user and adjust permissions
RUN useradd -m injaaz && chown -R injaaz /app
USER injaaz

# Render will provide PORT at runtime. Provide sane defaults for local testing.
ENV PORT=${PORT:-5000}
ENV WEB_CONCURRENCY=${WEB_CONCURRENCY:-1}

EXPOSE 5000

# Use shell form so environment variables like ${PORT} are expanded at runtime.
CMD sh -c "gunicorn wsgi:app -w ${WEB_CONCURRENCY:-1} --threads 4 --bind 0.0.0.0:${PORT:-5000}"