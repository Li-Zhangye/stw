FROM python:3.11-slim

LABEL maintainer="sms2web" description="短信转网页 SMS2Web"

ENV DATA_DIR=/data \
    MOD_DIR=/mod \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd -r appuser && useradd -r -g appuser -u 1000 appuser && chown -R appuser:appuser /app /data /mod

COPY --chown=appuser:appuser server/ server/
COPY --chown=appuser:appuser public/ public/

EXPOSE 19672 19673

VOLUME ["/data", "/mod"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:19672/')" || exit 1

USER appuser

CMD ["python3", "server/server.py"]
