---
description: Deploy the Video Conversion System to Minikube
---

## 1. Start Minikube
First, ensure Minikube is running.
```bash
minikube start --driver=docker
```

## 2. Connect to Minikube's Docker Daemon
This step is critical. It points your local docker client to Minikube's internal Docker engine. This allows us to build images directly inside Minikube so Kubernetes can see them (since we use `imagePullPolicy: Never`).

**PowerShell:**
```powershell
& minikube -p minikube docker-env --shell powershell | Invoke-Expression
```

**Bash:**
```bash
eval $(minikube docker-env)
```

## 3. Build Images (Inside Minikube)
Build the images. Since we are connected to Minikube, these images will be stored there.

```bash
docker build -t video-api:latest -f api/Dockerfile .
docker build -t video-worker:latest -f worker/Dockerfile .
docker build -t video-frontend:latest -f frontend/Dockerfile.k8s frontend/
```

## 4. Deploy to Kubernetes
Apply the manifests in the correct order.

```bash
# 1. Create Namespace
kubectl apply -f k8s/namespace.yaml

# 2. Configs and Secrets
kubectl apply -f k8s/configmap.yaml

# 3. Third-party Services (RabbitMQ, MinIO)
kubectl apply -f k8s/rabbitmq.yaml
kubectl apply -f k8s/minio.yaml
kubectl apply -f k8s/database-pvc.yaml

# 4. Application Services
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/worker-deployment.yaml
kubectl apply -f k8s/frontend-deployment.yaml
```

## 5. Verify Deployment
Check if pods are starting.

```bash
kubectl get pods -n video-processing
```

## 6. Access the Application
Since we are using Minikube, we usually use `minikube tunnel` or `minikube service` to expose LoadBalancers.

**Option A (Recommended): Minikube Tunnel**
Run this in a **separate terminal** and keep it running:
```bash
minikube tunnel
```
This will assign External IPs to your services.
Then you can access the frontend at `http://localhost` (or the IP assigned).

**Option B: Direct Service URL**
Get the direct URL for the frontend:
```bash
minikube service frontend -n video-processing
```
