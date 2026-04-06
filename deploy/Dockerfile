# For Fly.io only — Railway uses Nixpacks (nixpacks.toml), not this file.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .
COPY config/ config/
COPY src/ src/

RUN mkdir -p /data
ENV DATABASE_PATH=/data/linguabot.db

RUN useradd -m botuser && chown -R botuser:botuser /app /data
USER botuser

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "bot.py"]
