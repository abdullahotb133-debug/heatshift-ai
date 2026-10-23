FROM python:3.13-slim
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY src ./src
ENV PYTHONPATH=/app/src HEATSHIFT_MODE=deployment
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["python", "-m", "uvicorn", "heatshift_ai.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
