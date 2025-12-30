---
description: Deploy the Video Conversion System to Minikube
---

# Deploy to Minikube

This workflow deploys the Cloud Video Conversion System to a fresh Minikube cluster with monitoring and autoscaling.

## Prerequisites

Ensure you have the following installed:
- Docker Desktop (running)
- Minikube
- kubectl
- Helm
- Python 3.x (for testing scripts)

## Deployment Steps

// turbo-all

### 1. Run the Deployment Script

**PowerShell (Windows)**:
```powershell
.\scripts\deploy-minikube.ps1
```

This script will:
- Delete any existing Minikube cluster (clean slate)
- Start a fresh Minikube instance (4 CPUs, 8GB RAM)
- Connect to Minikube's Docker daemon
- Build all Docker images inside Minikube
- Install KEDA for autoscaling
- Install Prometheus + Grafana for monitoring
- Deploy all services to the `video-processing` namespace
- Configure autoscaling (1-10 workers, 5 messages/pod threshold)

### 2. Verify Deployment

Check that all pods are running:
```bash
kubectl get pods -n video-processing
```

Expected pods:
- `api-*` (2 replicas)
- `worker-*` (1+ replicas, scaled by KEDA)
- `rabbitmq-*` (1 replica)
- `minio-*` (1 replica)
- `frontend-*` (1 replica)

### 3. Access the Application

**Frontend UI** (recommended):
```bash
minikube service frontend -n video-processing
```
This will automatically open your browser.

**API Documentation**:
```bash
minikube service api -n video-processing
```
Then navigate to `/docs` for Swagger UI.

### 4. Access Monitoring

**Grafana Dashboard**:
```bash
kubectl port-forward svc/prometheus-grafana 3000:80 -n monitoring
```
Open http://localhost:3000 (admin/admin)

**RabbitMQ Management**:
```bash
kubectl port-forward svc/rabbitmq 15672:15672 -n video-processing
```
Open http://localhost:15672 (guest/guest)

**MinIO Console**:
```bash
kubectl port-forward svc/minio 9001:9001 -n video-processing
```
Open http://localhost:9001 (minioadmin/minioadmin)

## Load Testing

### Run Performance Baseline Test

First, port-forward the API:
```bash
kubectl port-forward svc/api 8000:8000 -n video-processing
```

Then run load tests with different video sizes:
```bash
# 10MB videos (fast conversion)
python scripts/load-generator.py --api-url http://localhost:8000 --jobs 50 --video-size 10 --monitor

# 50MB videos
python scripts/load-generator.py --api-url http://localhost:8000 --jobs 30 --video-size 50

# 100MB videos (slower, triggers more scaling)
python scripts/load-generator.py --api-url http://localhost:8000 --jobs 20 --video-size 100
```

Watch the autoscaler in action:
```bash
kubectl get hpa -n video-processing -w
kubectl get pods -n video-processing -l app=worker -w
```

## Fault Tolerance Testing

Run fault tolerance tests to verify system resilience:

```bash
# Test pod termination (job requeuing)
python scripts/fault-tolerance-test.py pod-kill

# Test network latency (degraded performance)  
python scripts/fault-tolerance-test.py network-latency

# Test CPU pressure (resource contention)
python scripts/fault-tolerance-test.py cpu-pressure

# Run all tests
python scripts/fault-tolerance-test.py all
```

Monitor the results in Grafana to see how the system handles faults.

## Results Documentation

Document your test results in:
```
docs/PERFORMANCE_TESTING_RESULTS.md
```

This template includes tables for:
- Baseline performance by video size
- Scalability behavior (queue depth vs workers)
- Fault tolerance results
- Resource utilization metrics

## Troubleshooting

**Pods not starting**:
```bash
kubectl describe pod <pod-name> -n video-processing
kubectl logs <pod-name> -n video-processing
```

**Check KEDA ScaledObject**:
```bash
kubectl get scaledobject -n video-processing
kubectl describe scaledobject worker-scaledobject -n video-processing
```

**MinIO not accessible**:
```bash
kubectl logs -l app=minio -n video-processing
kubectl logs -l job-name=minio-init -n video-processing
```

## Clean Up

To remove everything:
```bash
minikube delete
```

