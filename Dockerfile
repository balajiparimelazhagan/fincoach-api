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

# Copy project files
COPY . /usr/app/

# Set permissions for entrypoint scripts
RUN chmod +x /usr/app/scripts/entrypoint.sh /usr/app/scripts/celery_worker_entrypoint.sh /usr/app/scripts/celery_beat_entrypoint.sh /usr/app/scripts/wait_for_db.py

# Set entrypoint
ENTRYPOINT ["/usr/app/scripts/entrypoint.sh"]