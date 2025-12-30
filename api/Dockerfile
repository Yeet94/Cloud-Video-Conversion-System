FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy shared module first
COPY shared/ /app/shared/

# Copy API requirements and install
COPY api/requirements.txt /app/api/
RUN pip install --no-cache-dir -r /app/api/requirements.txt

# Copy API application
COPY api/ /app/api/

# Create data directory for database
RUN mkdir -p /data

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
