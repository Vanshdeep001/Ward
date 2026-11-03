1# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install dependencies into an isolated prefix so only what we need goes in.
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy installed packages from builder.
COPY --from=builder /install /usr/local

# Copy application source.
COPY . .

# Non-root user for safety.
RUN adduser --disabled-password --gecos "" warduser \
    && chown -R warduser /app
USER warduser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

