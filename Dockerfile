FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev
RUN .venv/bin/playwright install --with-deps chromium

ENV PATH="/app/.venv/bin:${PATH}"

CMD ["ns-hotopic", "service-run"]
