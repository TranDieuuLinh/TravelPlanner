FROM mcr.microsoft.com/playwright/python:v1.62.0-noble

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

ARG PIP_INDEX_URL

RUN python -m pip install --no-cache-dir \
    --index-url "${PIP_INDEX_URL}" \
    --retries 10 \
    --timeout 120 \
    "."

ENV PYTHONPATH=/app/src
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
