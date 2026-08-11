FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple/

RUN python -m pip install --no-cache-dir \
    --index-url "${PIP_INDEX_URL}" \
    --retries 10 \
    --timeout 120 \
    "."

ENV PYTHONPATH=/app/src
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
