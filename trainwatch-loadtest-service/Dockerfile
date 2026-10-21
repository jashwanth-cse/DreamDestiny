FROM python:3.11-slim

WORKDIR /app

# Ensure output is sent straight to terminal without buffering
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Run as non-privileged user for least-privilege container security
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/sh appuser && \
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8080

# Cloud Run injects $PORT (default 8080); dynamic shell expansion ensures proper binding
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 2"]
