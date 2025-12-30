# Docker Compose - Local Development Guide

This guide covers running the Cloud Video Conversion System locally using Docker Compose for development and testing.

## Prerequisites

- **Docker Desktop** (Windows/Mac) or Docker Engine (Linux)
- **Docker Compose** v2.0+
- **Git** (to clone the repository)

### Verify Installation

```bash
docker --version
docker-compose --version
```

## Quick Start

### 1. Start All Services

Navigate to the project directory and start all services:

```bash
cd "Cloud Video Conversion System"

# Start all services in detached mode
docker-compose up -d

# Check service status
docker-compose ps

# View logs
docker-compose logs -f
```

### 2. Access the Application

Once all services are running, access the following endpoints:

| Service | URL | Credentials |
|---------|-----|-------------|
| **Frontend** | http://localhost | N/A |
| **API** | http://localhost:8000 | N/A |
| **API Docs** | http://localhost:8000/docs | N/A |
| **RabbitMQ Management** | http://localhost:15672 | guest/guest |
| **MinIO Console** | http://localhost:9001 | minioadmin/minioadmin |
| **Prometheus** | http://localhost:9090 | N/A |
| **Grafana** | http://localhost:3000 | admin/admin |

### 3. Import Grafana Dashboard

1. Navigate to **http://localhost:3000**
2. Login with `admin` / `admin`
3. Go to **Dashboards → Import**
4. Upload: `monitoring/grafana/dashboards/video-processing.json`
5. Select datasource: **Prometheus**
6. Click **Import**

## Testing the System

### Upload and Convert a Video

**Option 1: Using the Frontend**
1. Open http://localhost in your browser
2. Click "Upload Video"
3. Select a video file (AVI, MOV, MKV, etc.)
4. Choose output format (MP4 recommended)
5. Monitor conversion progress
6. Download the converted video

**Option 2: Using the API**

**Step 1: Request upload URL**
```bash
curl -X POST http://localhost:8000/upload/request \
  -H "Content-Type: application/json" \
  -d '{"filename": "my_video.avi", "content_type": "video/avi"}'
```

Response:
```json
{
  "upload_url": "http://localhost:9000/videos/uploads/abc123.avi?...",
  "object_path": "uploads/abc123.avi",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "expires_in": 3600
}
```

**Step 2: Upload file to presigned URL**
```bash
curl -X PUT "UPLOAD_URL_FROM_STEP_1" \
  -H "Content-Type: video/avi" \
  --data-binary @my_video.avi
```

**Step 3: Create conversion job**
```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "input_path": "uploads/abc123.avi",
    "output_format": "mp4"
  }'
```

**Step 4: Check job status**
```bash
curl http://localhost:8000/jobs/{job_id}
```

**Step 5: Download converted video**
```bash
curl http://localhost:8000/download/{job_id} -o output.mp4
```

## Monitoring

### Viewing Metrics in Grafana

The pre-configured Grafana dashboard includes:

1. **Throughput** - Videos processed per minute
2. **Scalability** - Queue depth vs worker pods (dual axis)
3. **Error Rates** - Errors per minute by type
4. **Conversion Performance** - P50/P95/P99 latencies

### Prometheus Metrics

Key metrics exposed by the system:

| Metric | Type | Description |
|--------|------|-------------|
| `api_requests_total` | Counter | Total API requests by endpoint |
| `api_ingestion_rate_total` | Counter | Video uploads and job creations |
| `api_request_duration_seconds` | Histogram | API request latency |
| `worker_jobs_processed_total` | Counter | Jobs processed by status |
| `worker_conversion_time_seconds` | Histogram | FFmpeg conversion time |
| `worker_failure_rate_total` | Counter | Failures by type |
| `worker_active_jobs` | Gauge | Currently processing jobs |

## Scaling Workers

To test scalability metrics in Grafana, manually scale the worker service:

```bash
# Scale to 3 workers
docker-compose up -d --scale worker=3

# Scale back to 1 worker
docker-compose up -d --scale worker=1
```

Prometheus will automatically discover the new worker instances.

## Load Testing

### Using Locust

Start the Locust load testing service:

```bash
# Start Locust
docker-compose -f docker-compose.locust.yml up -d

# Open Locust UI
# http://localhost:8089
```

**Recommended test settings:**
- **Number of users:** 50
- **Spawn rate:** 5 users/second
- **Host:** http://api:8000

### Test Scenarios

The load test includes two user types:

1. **VideoProcessingUser** - Simulates normal user behavior
   - Request upload URL
   - Create conversion jobs
   - Poll job status
   - Download completed videos

2. **BurstUser** - Simulates spike traffic
   - Rapid job creation
   - Tests message queue behavior

## Configuration

### Environment Variables

Key environment variables are defined in `docker-compose.yaml`:

| Variable | Default | Description |
|----------|---------|-------------|
| `RABBITMQ_HOST` | rabbitmq | RabbitMQ hostname |
| `RABBITMQ_PORT` | 5672 | RabbitMQ port |
| `RABBITMQ_USER` | guest | RabbitMQ username |
| `RABBITMQ_PASSWORD` | guest | RabbitMQ password |
| `RABBITMQ_QUEUE` | video-jobs | Queue name |
| `MINIO_ENDPOINT` | minio:9000 | MinIO endpoint |
| `MINIO_ACCESS_KEY` | minioadmin | MinIO access key |
| `MINIO_SECRET_KEY` | minioadmin | MinIO secret key |
| `MINIO_BUCKET` | videos | Bucket name |
| `DATABASE_PATH` | /data/jobs.db | SQLite database path |

### FFmpeg Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `FFMPEG_OUTPUT_FORMAT` | mp4 | Default output format |
| `FFMPEG_VIDEO_CODEC` | libx264 | Video codec |
| `FFMPEG_AUDIO_CODEC` | aac | Audio codec |
| `FFMPEG_PRESET` | medium | Encoding speed/quality |
| `FFMPEG_CRF` | 23 | Quality (0-51, lower=better) |

## Managing Services

### Useful Commands

```bash
# View logs for all services
docker-compose logs -f

# View logs for specific service
docker-compose logs -f api
docker-compose logs -f worker

# Restart a specific service
docker-compose restart api

# Stop all services
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v

# Rebuild images after code changes
docker-compose build
docker-compose up -d
```

## Troubleshooting

For common issues and solutions, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Next Steps

- **Architecture Deep Dive**: See [docs/ARCHITECTURE.md](../ARCHITECTURE.md) for detailed component interactions
- **Kubernetes Deployment**: See [docs/kubernetes/MINIKUBE.md](../kubernetes/MINIKUBE.md) for K8s deployment
- **Performance Testing**: See [docs/PERFORMANCE_TESTING.md](../PERFORMANCE_TESTING.md) for benchmarks

---

**Built for local development and testing** | For production deployments, see [Kubernetes guides](../kubernetes/)
