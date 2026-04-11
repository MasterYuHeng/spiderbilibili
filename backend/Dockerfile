FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    HOME=/home/appuser

WORKDIR /app

COPY backend/requirements.txt /tmp/requirements.txt

RUN pip install --upgrade pip \
    && pip install -r /tmp/requirements.txt \
    && rm -rf /root/.cache/pip

RUN useradd --create-home --home-dir /home/appuser --shell /bin/bash appuser

COPY backend /app

RUN mkdir -p /app/logs /app/data/raw \
    && chown -R appuser:appuser /app /home/appuser /ms-playwright

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
