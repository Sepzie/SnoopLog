FROM python:3.12-slim

RUN groupadd -r snooplog && useradd -r -g snooplog snooplog

WORKDIR /app

# Build context is repo root (see docker-compose.yml)
COPY pipeline/requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt

COPY shared/ /app/shared/
COPY pipeline/ /app/pipeline/
COPY snooplog.yaml /app/snooplog.yaml

USER snooplog
COPY pipeline/docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 3001

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "pipeline.main:app", "--host", "0.0.0.0", "--port", "3001"]
