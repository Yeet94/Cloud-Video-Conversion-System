FROM python:3.11-slim

WORKDIR /locust

# Install Locust
RUN pip install --no-cache-dir locust

# Copy the locustfile
COPY tests/load/locustfile.py /locust/locustfile.py

# Copy local test video
RUN mkdir -p /mnt/locust
COPY test_video.mp4 /mnt/locust/sample.mp4

EXPOSE 8089 5557

CMD ["locust", "-f", "/locust/locustfile.py"]
