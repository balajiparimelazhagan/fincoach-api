# Use a smaller base image
FROM python:3.11-slim

# Set work directory
WORKDIR /usr/app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies (added netcat for healthchecks)
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential libssl-dev libffi-dev libpq-dev netcat-traditional && \
    rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt /usr/app/
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -rf /root/.cache/pip

# Copy entrypoint scripts and utility scripts, set permissions
COPY entrypoint.sh /usr/app/entrypoint.sh
COPY celery_worker_entrypoint.sh /usr/app/celery_worker_entrypoint.sh
COPY celery_beat_entrypoint.sh /usr/app/celery_beat_entrypoint.sh
COPY wait_for_db.py /usr/app/wait_for_db.py
RUN chmod +x /usr/app/entrypoint.sh /usr/app/celery_worker_entrypoint.sh /usr/app/celery_beat_entrypoint.sh /usr/app/wait_for_db.py

# Copy project files
COPY . /usr/app/

# Set entrypoint
ENTRYPOINT ["/usr/app/entrypoint.sh"]