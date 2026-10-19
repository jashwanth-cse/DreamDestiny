FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY transport-service/train/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service source code
COPY transport-service/train/ .

# Copy the dataset into the container's /app/data folder
COPY data/railway_stations.json /app/data/railway_stations.json

ENV RAILWAY_STATIONS_DATA_PATH=/app/data/railway_stations.json
ENV PORT=8005

RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/sh appuser && \
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8005

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005", "--workers", "2"]