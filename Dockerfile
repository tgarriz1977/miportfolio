FROM python:3.13-slim-bookworm

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code. Every module app.py imports has to be listed here — a missing
# one only fails at container start, not at build time.
COPY app.py sources.py llm.py youtube.py index.html ./
RUN mkdir -p /data

EXPOSE 5050

ENV PORTFOLIO_DB=/data/portfolio.db
ENV HOST=0.0.0.0
ENV PORT=5050

CMD ["python3", "app.py"]
