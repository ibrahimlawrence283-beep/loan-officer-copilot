FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY evals ./evals

# run as a non-root user; the audit database lives in /data
RUN useradd --create-home appuser && mkdir /data && chown appuser /data
USER appuser
ENV AUDIT_DB=/data/audit.db

EXPOSE 8000
# the model trains at startup (about 15 seconds), so allow time before health checks fail
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
