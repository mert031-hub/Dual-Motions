# syntax=docker/dockerfile:1
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    RESEARCH_DATA_DIR=/app/runtime CASES_EXPERT_JSON=/app/runtime/cases_expert.json \
    APP_REQUIRE_AUTH=1
WORKDIR /app
COPY requirements.lock ./
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then \
      PIP_CERT=/run/secrets/build_ca pip install --no-cache-dir --require-hashes -r requirements.lock; \
    else \
      pip install --no-cache-dir --require-hashes -r requirements.lock; \
    fi
RUN groupadd --gid 10001 researcher && useradd --uid 10001 --gid researcher --no-create-home researcher
COPY --chown=researcher:researcher . .
RUN mkdir -p /app/runtime && chown researcher:researcher /app/runtime
USER researcher
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health',timeout=3)"
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
