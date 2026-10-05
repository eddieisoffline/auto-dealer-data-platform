FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir ".[gcs,kaggle,bigquery]"

# Cloud Run Jobs ejecuta: python -m pipeline.cli ingest --date YYYY-MM-DD
ENTRYPOINT ["python", "-m", "pipeline.cli"]
