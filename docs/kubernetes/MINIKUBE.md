# Kubernetes Deployment - Minikube Guide

This guide provides comprehensive instructions for deploying the Cloud Video Conversion System on Minikube for local Kubernetes development and testing.

## Overview

This deployment demonstrates:
- **Event-driven autoscaling** with KEDA (1-10 workers based on queue depth)
- **Horizontal Pod Autoscaling** (HPA) in action
- **Monitoring and observability** with Prometheus + Grafana
- **Fault tolerance** and job recovery
- **Production-like architecture** on your local machine

## Prerequisites

### Required Software

- **Docker Desktop** (Windows/Mac) or Docker Engine (Linux)
- **Minikube** v1.30+
- **kubectl** v1.27+
- **Helm** 3.x
- **Python 3.11+** (for load generation scripts)

### System Requirements

- **CPU**: 4+ cores recommended
- **RAM**: 8GB+ recommended (Minikube will use ~4-6GB)
- **Disk**: 20GB+ free space

### Install Tools

**Windows (using winget):**
```powershell
# Install Docker Desktop
winget install Docker.DockerDesktop

# Install Minikube
winget install Kubernetes.minikube

# Install kubectl
winget install Kubernetes.kubectl

# Install Helm
winget install Helm.Helm
```

**Mac (using Homebrew):**
```bash
brew install minikube kubectl helm
```

**Verify installations:**
```bash
docker --version
minikube version
kubectl version --client
helm version
```

## Quick Start (Automated)

### Option 1: Automated Deployment Script

The fastest way to deploy:

```powershell
# Navigate to project directory
cd "Cloud Video Conversion System"

# Run automated deployment script
.\scripts\deploy-minikube.ps1
```

This script will:
1. ✅ Delete any existing Minikube cluster (clean start)
2. ✅ Start fresh Minikube (4 CPUs, 8GB RAM)
3. ✅ Build all Docker images inside Minikube
4. ✅ Install KEDA for autoscaling
5. ✅ Install Prometheus + Grafana for monitoring
6. ✅ Deploy all services to `video-processing` namespace
7. ✅ Configure autoscaling (1-10 workers, 5 msg/pod threshold)

**Expected deployment time**: 5-10 minutes

Skip to [Accessing Services](#accessing-services) after the script completes.

---

## Manual Deployment (Step-by-Step)

### 1. Start Minikube

Start Minikube with appropriate resources:

```bash
# Delete existing cluster if present (clean start)
minikube delete

# Start fresh Minikube instance
minikube start --cpus=4 --memory=8192 --driver=docker
```

> **Note:** If you have limited RAM, you can use `--memory=4096`, but reduce concurrent workers for tests.

### 2. Enable Required Addons

```bash
# Enable Ingress (for routing)
minikube addons enable ingress

# Enable Metrics Server (for kubectl top)
minikube addons enable metrics-server

# Verify Minikube is running
kubectl cluster-info
kubectl get nodes
```

### 3. Build Docker Images

Configure Docker to use Minikube's registry:

```bash
# Windows (PowerShell)
& minikube -p minikube docker-env --shell powershell | Invoke-Expression

# Mac/Linux (Bash)
eval $(minikube docker-env)
```

> **Important:** Run this in each new terminal session before building images.

Build all images:

```bash
# Build API
docker build -t video-api:latest -f api/Dockerfile .

# Build Worker
docker build -t video-worker:latest -f worker/Dockerfile .

# Build Frontend
docker build -t video-frontend:latest -f frontend/Dockerfile .

# Build Locust (for load testing)
docker build -t locust-load:latest -f tests/load/Dockerfile .

# Verify images
docker images | findstr video
```

### 4. Create Namespaces

```bash
kubectl create namespace video-processing
kubectl create namespace monitoring
```

### 5. Install KEDA (Autoscaling)

```bash
# Install KEDA
kubectl apply -f https://github.com/kedacore/keda/releases/download/v2.12.0/keda-2.12.0.yaml

# Wait for KEDA pods to be ready
kubectl get pods -n keda --watch
# Press Ctrl+C once all pods show "Running"
```

### 6. Install Prometheus & Grafana

```bash
# Add Prometheus Helm repo
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Install Prometheus Stack
helm install prometheus prometheus-community/kube-prometheus-stack \
  --set grafana.adminPassword=admin \
  -n monitoring

# Wait for all monitoring pods
kubectl get pods -n monitoring --watch
# Press Ctrl+C when all pods are Running
```

### 7. Deploy Application Components

Apply manifests in the correct order:

```bash
# ConfigMap (environment variables)
kubectl apply -f k8s/configmap.yaml

# Storage layer
kubectl apply -f k8s/database-pvc.yaml
kubectl apply -f k8s/minio.yaml
kubectl apply -f k8s/rabbitmq.yaml

# Application layer
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/worker-deployment.yaml
kubectl apply -f k8s/frontend-deployment.yaml

# Autoscaling
kubectl apply -f k8s/keda-scaledobject.yaml

# Ingress
kubectl apply -f k8s/ingress.yaml

# Monitoring (ServiceMonitors)
kubectl apply -f k8s/monitoring/

# Load Testing (optional but recommended for demos)
kubectl apply -f k8s/locust-deployment.yaml

# Verify all pods are running
kubectl get pods -n video-processing
kubectl get pods -n monitoring
```

Wait 2-5 minutes for all pods to reach `Running` status.

---

## Accessing Services

### Start Minikube Tunnel

**Required for Ingress to work:**

```bash
# Run in a separate terminal - keep it running
minikube tunnel
```

This command requires admin privileges. Leave it running while using the application.

**Note:** The tunnel is required for `http://localhost` access via Ingress. Admin tools (below) use port-forward and don't need the tunnel.

### Main Application

Once the tunnel is running:

- **Frontend**: http://localhost
- **API**: http://localhost/api
- **API Health**: http://localhost/api/health
- **API Docs**: http://localhost/api/docs

### Admin Interfaces (Port Forwarding)

Use port-forwarding for admin tools:

**Grafana (Monitoring Dashboard):**
```bash
kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80
```
- URL: **http://localhost:3000**
- Login: `admin` / `admin`

**MinIO Console (Object Storage):**
```bash
kubectl port-forward -n video-processing svc/minio 9001:9001
```
- URL: **http://localhost:9001**
- Login: `minioadmin` / `minioadmin`

**RabbitMQ Management (Message Queue):**
```bash
kubectl port-forward -n video-processing svc/rabbitmq 15672:15672
```
- URL: **http://localhost:15672**
- Login: `guest` / `guest`

### Import Grafana Dashboard

1. Navigate to **http://localhost:3000**
2. Login with `admin` / `admin`
3. Go to **Dashboards → Import**
4. Upload: `monitoring/grafana/dashboards/video-processing.json`
5. Select datasource: **Prometheus**
6. Click **Import**

---

## Testing & Validation

### 1. Basic Functionality Test

Test video upload and conversion:

```bash
# Access frontend
# http://localhost

# Upload a test video through the UI
# Monitor progress in Grafana dashboard
```

### 2. Load Testing (Recommended)

**Use the Python load generator for reliable end-to-end testing:**

```bash
# Light test (20 jobs, 10MB videos)
python scripts/load-generator.py --api-url http://localhost/api --jobs 20 --video-size 10 --monitor

# Medium test (50 jobs, 25MB videos)
python scripts/load-generator.py --api-url http://localhost/api --jobs 50 --video-size 25 --monitor

# Heavy test (100 jobs, 10MB videos, 10 concurrent)
python scripts/load-generator.py --api-url http://localhost/api --jobs 100 --video-size 10 --concurrent 10 --monitor
```

**Why load-generator.py instead of Locust?**
- ✅ Properly uploads real videos to MinIO via presigned URLs
- ✅ Tracks job completion and success rates
- ✅ Shows live KEDA scaling status
- ✅ Easier to use for demos

**Optional - Locust Web UI:**

Locust is available but has limitations with MinIO presigned URL uploads:

```bash
# Access Locust UI
kubectl port-forward -n video-processing svc/locust-master 8089:8089
# Visit http://localhost:8089

# Note: Jobs may fail with "Failed to download input file"
# due to presigned URL upload issues. Use load-generator.py instead.
```

### 3. Autoscaling Demonstration (KEDA)

Watch KEDA scale workers based on RabbitMQ queue depth:

```bash
# Terminal 1: Watch worker pods
kubectl get pods -n video-processing -l app=worker -w

# Terminal 2: Watch HPA
kubectl get hpa -n video-processing -w

# Terminal 3: Generate load
python scripts/load-generator.py --api-url http://localhost:8000 --jobs 100 --video-size 10 --monitor
```

**Expected behavior:**
- Queue depth increases → Workers scale up (5 messages per pod threshold)
- Queue drains → Workers scale down after 30s cooldown
- Min: 1 worker, Max: 10 workers

**Monitor in Grafana:**
- Open http://localhost:3000
- View "Scalability" panel showing Queue Depth vs Worker Pods
- Should see correlation between queue size and pod count

### 4. Fault Tolerance Tests

Verify system resilience:

**Test 1: Worker Pod Termination**
```bash
# While jobs are running, kill a worker pod
kubectl delete pod -n video-processing -l app=worker --wait=false

# Verify: Job gets requeued and completed by another worker
# Check RabbitMQ: http://localhost:15672 → Queues
```

**Test 2: CPU Pressure**
```bash
# Apply CPU stress to a worker pod
kubectl exec -it -n video-processing deployment/worker -- stress-ng --cpu 2 --timeout 60s

# Verify: Jobs slow down but don't fail
# Monitor in Grafana dashboard
```

**Test 3: Network Latency**
```bash
# Run fault tolerance test script
python scripts/fault-tolerance-test.py network-latency

# Observe increased conversion times in Grafana
```

---

## Monitoring & Observability

### Grafana Dashboards

The pre-configured dashboard includes:

1. **Throughput**: Videos processed per minute (success/fail)
2. **Scalability**: Queue depth vs worker pod count
3. **Performance**: Conversion time percentiles (P50/P95/P99)
4. **Error Rates**: Failed jobs by failure type
5. **Resource Usage**: CPU/Memory per component
6. **Business Metrics**: Total jobs, active workers

### Key Metrics

| Metric | Description | Alert Threshold |
|--------|-------------|----------------|
| `worker_jobs_processed_total` | Total jobs completed | - |
| `rabbitmq_queue_depth` | Messages in queue | > 50 |
| `worker_conversion_time_seconds` | Video conversion duration | P95 > 60s |
| `worker_failure_rate_total` | Job failures by type | > 5% |
| `up{job="worker"}` | Worker pod count | < 1 |

---

## Configuration

### KEDA Autoscaling

Configuration in `k8s/keda-scaledobject.yaml`:

```yaml
minReplicaCount: 1
maxReplicaCount: 10
queueLength: 5  # messages per worker
pollingInterval: 10s
cooldownPeriod: 30s
```

### Worker Resources

Configuration in `k8s/worker-deployment.yaml`:

```yaml
resources:
  requests:
    cpu: 500m
    memory: 512Mi
  limits:
    cpu: 2000m
    memory: 2Gi
```

### Database

- **Type**: SQLite (development only)
- **Storage**: PersistentVolumeClaim (ReadWriteMany)
- **Path**: `/data/jobs.db`
- **Shared by**: API pods (2 replicas) + Worker pods (1-10 replicas)

> **Production Note**: Replace SQLite with PostgreSQL/MySQL for true multi-writer support.

---

## Troubleshooting

For Kubernetes-specific troubleshooting, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

### Quick Diagnostics

```bash
# View all resources
kubectl get all -n video-processing

# Check pod status
kubectl get pods -n video-processing
kubectl describe pod <pod-name> -n video-processing

# View logs
kubectl logs -f -l app=worker -n video-processing
kubectl logs -f -l app=api -n video-processing

# Check KEDA scaling
kubectl get scaledobject -n video-processing
kubectl describe scaledobject worker-scaledobject -n video-processing

# View events
kubectl get events -n video-processing --sort-by='.lastTimestamp'
```

### Common Issues

**Problem: "Failed to create job" / 500 errors when uploading**

**Cause:** RabbitMQ connection has become stale after running for several hours.

**Solution:**
```bash
# Restart API pods to refresh RabbitMQ connections
kubectl rollout restart deployment/api -n video-processing
kubectl wait --for=condition=ready pod -l app=api -n video-processing
```

**Note:** The API code now includes automatic reconnection logic, but a manual restart ensures fresh connections before demos.

---

**Problem: Grafana dashboard shows "No data" for metrics**

**Cause:** Prometheus ServiceMonitor not scraping metrics (usually fixed in current version).

**Solution:**
```bash
# Check if Prometheus is scraping the API
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090

# Visit http://localhost:9090 and query: rabbitmq_queue_depth
# If empty, check ServiceMonitor configuration
kubectl get servicemon itors -n monitoring
```

---

**Problem: Pods stuck in "ContainerCreating"**

**Cause:** Docker image not built or missing in Minikube's Docker daemon.

**Solution:**
```bash
# Switch to Minikube's Docker
& minikube -p minikube docker-env --shell powershell | Invoke-Expression

# Rebuild missing image
docker build -t video-api:latest -f api/Dockerfile .
docker build -t video-worker:latest -f worker/Dockerfile .
docker build -t video-frontend:latest -f frontend/Dockerfile .

# Restart deployment
kubectl rollout restart deployment/<deployment-name> -n video-processing
```

---

**Problem: "Bucket does not exist" errors**

**Cause:** MinIO init job failed or completed before MinIO was ready.

**Solution:**
```bash
# Check if bucket exists (requires port-forward to MinIO)
kubectl port-forward -n video-processing svc/minio 9000:9000

# Create bucket manually via Python
python -c "from minio import Minio; client = Minio('localhost:9000', access_key='minioadmin', secret_key='minioadmin', secure=False); client.make_bucket('videos'); print('Bucket created!')"
```

---

## Cleanup

### Stop Services (Keep Minikube)

```bash
kubectl delete namespace video-processing
kubectl delete namespace monitoring
```

### Full Cleanup

```bash
# Delete everything and stop Minikube
minikube delete

# Optional: Remove Docker images
docker rmi video-api:latest video-worker:latest video-frontend:latest
```

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────┐
│                      Minikube Cluster                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐       │
│  │  Frontend   │  │     API     │  │ Worker (1-10)│       │
│  │   (Nginx)   │  │  (FastAPI)  │  │  (FFmpeg)    │       │
│  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘       │
│         │                │                 │               │
│         └────────┬───────┴─────────────────┘               │
│                  │                                         │
│  ┌───────────────▼────────────────────────────────┐       │
│  │            Ingress Controller                  │       │
│  │  (Routes: /, /api, /minio, /rabbitmq)         │       │
│  └────────────────────────────────────────────────┘       │
│                  │                                         │
│  ┌───────────────▼────────┐  ┌──────────────────┐        │
│  │  MinIO (Object Store)  │  │ RabbitMQ (Queue) │        │
│  └────────────────────────┘  └──────────────────┘        │
│                                                             │
│  ┌─────────────────────────────────────────────┐          │
│  │  KEDA (Autoscaler)                          │          │
│  │  Scales Worker: 1-10 based on queue depth   │          │
│  └─────────────────────────────────────────────┘          │
│                                                             │
│  ┌─────────────────────────────────────────────┐          │
│  │  Monitoring Stack                           │          │
│  │  - Prometheus (Metrics)                     │          │
│  │  - Grafana (Dashboard)                      │          │
│  └─────────────────────────────────────────────┘          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
         ▲
         │ minikube tunnel
         │
    ┌────┴─────┐
    │ Localhost│
    │  :80     │
    └──────────┘
```

---

## Next Steps

- **Architecture Deep Dive**: See [docs/ARCHITECTURE.md](../ARCHITECTURE.md)
- **Performance Testing**: See [docs/PERFORMANCE_TESTING.md](../PERFORMANCE_TESTING.md)
- **Production Deployment**: See [PRODUCTION.md](PRODUCTION.md)
- **Docker Compose (Local)**: See [docs/local/DOCKER_COMPOSE.md](../local/DOCKER_COMPOSE.md)

---

**Last Updated:** 2025-12-30  
**Tested On:** Minikube v1.32, Kubernetes v1.28, Windows 11 & macOS
