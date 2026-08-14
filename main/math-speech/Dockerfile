FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY vietnamese_renderer.py .
COPY vendor ./vendor
COPY rules_overrides ./rules_overrides
COPY scripts/apply_rule_overrides.py ./scripts/

# Build the effective rules tree; fails loudly if upstream text stopped matching.
RUN python scripts/apply_rule_overrides.py

RUN useradd --create-home --uid 10001 mathspeech \
    && chown -R mathspeech:mathspeech /app/rules /app/vendor/Rules
USER mathspeech

EXPOSE 8100
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/health', timeout=2)"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8100", "--workers", "1"]
