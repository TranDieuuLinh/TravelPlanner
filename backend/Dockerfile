FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    for attempt in 1 2 3; do \
        python -m pip install \
            --disable-pip-version-check \
            --retries 10 \
            --timeout 120 \
            -r requirements.txt && exit 0; \
        if [ "$attempt" -eq 3 ]; then exit 1; fi; \
        echo "pip install failed (attempt $attempt/3); retrying..."; \
    done

COPY . .

RUN sed -i 's/\r$//' /app/scripts/docker-entrypoint.sh \
    && chmod +x /app/scripts/docker-entrypoint.sh

CMD ["/app/scripts/docker-entrypoint.sh"]
