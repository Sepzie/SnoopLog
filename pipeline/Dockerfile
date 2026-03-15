FROM python:3.12-slim

RUN groupadd -r snooplog && useradd -r -g snooplog snooplog

WORKDIR /app

# Build context is repo root (see docker-compose.yml)
COPY pipeline/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /app/shared/
COPY pipeline/ /app/pipeline/
COPY snooplog.yaml /app/snooplog.yaml

# Pre-create writable dirs so the non-root user owns them at runtime
RUN mkdir -p /data /app/data && chown snooplog:snooplog /data /app/data

USER snooplog

EXPOSE 3001

CMD ["uvicorn", "pipeline.main:app", "--host", "0.0.0.0", "--port", "3001"]
