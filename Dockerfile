# ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .

RUN pip install --no-cache-dir --user -r requirements.txt

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim

# Install tini for proper signal handling (graceful shutdown)
RUN apt-get update && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy project source
COPY bot.py .
COPY config/ config/
COPY src/ src/

# Persistent data directory (mounted as a volume on Fly.io / Railway)
RUN mkdir -p /data
ENV DATABASE_PATH=/data/linguabot.db

# Non-root user for security
RUN useradd -m botuser && chown -R botuser:botuser /app /data
USER botuser

# Use tini as PID 1 so SIGTERM is forwarded correctly
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "bot.py"]
