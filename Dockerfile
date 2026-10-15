# Wizzy: the public, read-only bot (Telegram webhook + X poller + scroll site + workers) in one process.
# The heavymetal trading REPL is not started here, and Wizzy never loads a wallet.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    HEAVYMETAL_HOME=/data

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY heavymetal ./heavymetal
RUN uv sync --frozen --no-dev --extra wizzy \
    && useradd --create-home --uid 10001 wizzy \
    && mkdir -p /data && chown wizzy:wizzy /data

USER wizzy
VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz')"
CMD ["uv", "run", "--no-sync", "wizzy", "serve"]
