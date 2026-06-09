FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends docker.io postgresql-client && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backup_worker.py .
COPY restore_interactive.py .
COPY force_backup.py .

CMD ["python", "-u", "backup_worker.py"]
