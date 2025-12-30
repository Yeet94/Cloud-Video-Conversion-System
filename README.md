# Cloud Video Conversion System

A distributed, event-driven microservices application for scalable video processing using FastAPI, RabbitMQ, MinIO, FFmpeg, and KEDA autoscaling on Kubernetes.

> [!TIP]
> **New to the project?** Check out the [Architecture Guide](docs/ARCHITECTURE.md) for a deep dive into how components interact.

## 🏗️ System Overview

```mermaid
graph TD
    User([End User])
    
    subgraph "Ingestion Layer"
        LoadBalancer[K8s Service / Load Balancer]
        API[API Service - FastAPI]
    end
    
    subgraph "Messaging & State"
        RabbitMQ[(RabbitMQ Queue)]
        Database[(Database)]
    end
    
    subgraph "Storage Layer"
        MinIO[(MinIO Object Storage)]
    end
    
    subgraph "Processing Layer"
        Worker[Worker Service - FFmpeg]
        KEDA[KEDA Autoscaler]
    end
    
    subgraph "Monitoring"
        Prometheus[Prometheus]
        Grafana[Grafana]
    end

    User -->|1. Request Upload URL| API
    API -->|2. Generate Presigned URL| MinIO
    API -->|3. Return URL & JobID| User
    User -->|4. Upload Video| MinIO
    
    API -->|5. Enqueue Job| RabbitMQ
    API -->|6. Persist Job State| Database
    
    KEDA -->|Monitor Queue Depth| RabbitMQ
    KEDA -->|Scale Replicas| Worker
    
    Worker -->|7. Consume Job| RabbitMQ
    Worker -->|8. Download Video| MinIO
    Worker -->|9. Convert with FFmpeg| Worker
    Worker -->|10. Upload Output| MinIO
    Worker -->|11. Update Status| Database
    
    Prometheus -->|Scrape Metrics| API
    Prometheus -->|Scrape Metrics| Worker
    Grafana -->|Query| Prometheus
```

### Key Features

- **Event-Driven Architecture**: Asynchronous processing via RabbitMQ
- **Auto-Scaling**: KEDA scales workers (1-10 pods) based on queue depth
- **Fault Tolerance**: Job recovery and automatic retries
- **Monitoring**: Pre-configured Grafana dashboards with Prometheus metrics
- **Cloud-Native**: Designed for Kubernetes with production-ready patterns

---

## 🚀 Choose Your Deployment Method

### Option 1: Docker Compose (Local Development)

**Best for**: Local development, quick testing, and learning the system

```bash
docker-compose up -d
```

📖 **[Full Docker Compose Guide →](docs/local/DOCKER_COMPOSE.md)**

**Quick Access:**
- Frontend: http://localhost
- API: http://localhost:8000
- Grafana: http://localhost:3000 (admin/admin)
- RabbitMQ: http://localhost:15672 (guest/guest)
- MinIO: http://localhost:9001 (minioadmin/minioadmin)

---

### Option 2: Kubernetes on Minikube

**Best for**: Kubernetes learning, demonstrating autoscaling (HPA/KEDA), and fault tolerance

```powershell
# Automated deployment
.\scripts\deploy-minikube.ps1
```

📖 **[Full Minikube Guide →](docs/kubernetes/MINIKUBE.md)**

**Features Demonstrated:**
- KEDA autoscaling (1-10 workers)
- Prometheus + Grafana monitoring
- Fault tolerance and job recovery
- Horizontal Pod Autoscaling (HPA)

---

## 📚 Documentation

### Getting Started

- **[Architecture Overview](docs/ARCHITECTURE.md)** - Component interactions and data flow
- **[Docker Compose Setup](docs/local/DOCKER_COMPOSE.md)** - Local development guide
- **[Minikube Deployment](docs/kubernetes/MINIKUBE.md)** - Kubernetes testing guide

### Testing & Operations

- **[Performance Testing](docs/PERFORMANCE_TESTING.md)** - Load testing and benchmarks
- **[Troubleshooting (Docker Compose)](docs/local/TROUBLESHOOTING.md)** - Common Docker issues
- **[Troubleshooting (Kubernetes)](docs/kubernetes/TROUBLESHOOTING.md)** - Common K8s issues

---

## 📋 API Reference

### Upload and Convert a Video

**Step 1: Request upload URL**
```bash
curl -X POST http://localhost:8000/upload/request \
  -H "Content-Type: application/json" \
  -d '{"filename": "my_video.avi", "content_type": "video/avi"}'
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

### Additional Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/docs` | GET | Interactive API documentation (Swagger) |
| `/upload/request` | POST | Request presigned upload URL |
| `/jobs` | POST | Create conversion job |
| `/jobs` | GET | List all jobs (supports filtering) |
| `/jobs/{job_id}` | GET | Get job status |
| `/download/{job_id}` | GET | Get download URL for converted video |
| `/metrics` | GET | Prometheus metrics |

---

## 📊 Monitoring

### Grafana Dashboards

Pre-configured dashboards show:

1. **Throughput** - Videos processed per minute
2. **Scalability** - Queue depth vs worker pods
3. **Error Rates** - Errors per minute by type
4. **Conversion Performance** - P50/P95/P99 latencies
5. **Resource Usage** - CPU/Memory per component

### Key Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `api_requests_total` | Counter | Total API requests by endpoint |
| `api_ingestion_rate_total` | Counter | Video uploads and job creations |
| `api_request_duration_seconds` | Histogram | API request latency |
| `worker_jobs_processed_total` | Counter | Jobs processed by status |
| `worker_conversion_time_seconds` | Histogram | FFmpeg conversion time |
| `worker_failure_rate_total` | Counter | Failures by type |
| `worker_active_jobs` | Gauge | Currently processing jobs |

---

## 🧪 Load Testing

### Using Locust

**Docker Compose:**
```bash
docker-compose -f docker-compose.locust.yml up -d
# Visit http://localhost:8089
```

**Kubernetes:**
```bash
kubectl port-forward svc/locust-master 8089:8089 -n video-processing
# Visit http://localhost:8089
```

**Test Configuration:**
- Users: 50
- Spawn rate: 5 users/second
- Host: http://api:8000

### Using Load Generator Script

```bash
python scripts/load-generator.py --api-url http://localhost:8000 --jobs 100 --video-size 10
```

---

## 📁 Project Structure

```
Cloud Video Conversion System/
├── api/                        # FastAPI application
│   ├── main.py                 # API endpoints
│   ├── requirements.txt
│   └── Dockerfile
├── worker/                     # Video processing worker
│   ├── worker.py               # Worker logic
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                   # Web UI
│   ├── index.html
│   ├── app.js
│   └── Dockerfile
├── shared/                     # Shared utilities
│   ├── config.py               # Configuration
│   ├── models.py               # Data models
│   └── database.py             # Database operations
├── k8s/                        # Kubernetes manifests
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── api-deployment.yaml
│   ├── worker-deployment.yaml
│   ├── keda-scaledobject.yaml
│   └── monitoring/
├── monitoring/                 # Monitoring configuration
│   ├── prometheus.yml
│   └── grafana/
│       └── dashboards/
├── scripts/                    # Deployment and testing scripts
│   ├── deploy-minikube.ps1
│   ├── load-generator.py
│   └── fault-tolerance-test.py
├── docs/                       # Documentation
│   ├── ARCHITECTURE.md
│   ├── PERFORMANCE_TESTING.md
│   ├── local/                  # Docker Compose docs
│   │   ├── DOCKER_COMPOSE.md
│   │   └── TROUBLESHOOTING.md
│   └── kubernetes/             # Kubernetes docs
│       ├── MINIKUBE.md
│       ├── PRODUCTION.md
│       └── TROUBLESHOOTING.md
├── docker-compose.yaml         # Local development
├── docker-compose.locust.yml   # Load testing
└── README.md                   # This file
```

---

## ⚙️ Configuration

### Environment Variables

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

---

## 🔧 Troubleshooting

### Quick Diagnostics

**Docker Compose:**
```bash
docker-compose logs -f
docker-compose ps
```

**Kubernetes:**
```bash
kubectl get pods -n video-processing
kubectl logs -f -l app=worker -n video-processing
kubectl get events -n video-processing --sort-by='.lastTimestamp'
```

### Common Issues

- **[Docker Compose Troubleshooting →](docs/local/TROUBLESHOOTING.md)**
- **[Kubernetes Troubleshooting →](docs/kubernetes/TROUBLESHOOTING.md)**

---

## 📄 License

This project is for educational and demonstration purposes.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

---

**Built with** ❤️ **for demonstrating cloud-native best practices**
