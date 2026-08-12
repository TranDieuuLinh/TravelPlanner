FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    for index_url in https://pypi.org/simple/ https://pypi.python.org/simple/; do \
        python -m pip install \
            --isolated \
            --disable-pip-version-check \
            --no-cache-dir \
            --index-url "$index_url" \
            --retries 3 \
            --timeout 30 \
            -r requirements.txt && exit 0; \
        echo "pip install failed using $index_url; trying the fallback index..."; \
    done; \
    exit 1

COPY . .

RUN sed -i 's/\r$//' /app/scripts/docker-entrypoint.sh \
    && chmod +x /app/scripts/docker-entrypoint.sh

CMD ["/app/scripts/docker-entrypoint.sh"]
