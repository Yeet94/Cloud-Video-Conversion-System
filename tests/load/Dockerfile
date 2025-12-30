FROM python:3.11-slim

WORKDIR /locust

# Install Locust
RUN pip install --no-cache-dir locust

# Copy the locustfile
COPY tests/load/locustfile.py /locust/locustfile.py

# Create directory and dummy sample.mp4 for testing
# Download a valid sample video (~2MB)
RUN apt-get update && apt-get install -y curl && \
    mkdir -p /mnt/locust && \
    curl -L -o /mnt/locust/sample.mp4 https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4 && \
    rm -rf /var/lib/apt/lists/*

EXPOSE 8089 5557

CMD ["locust", "-f", "/locust/locustfile.py"]
