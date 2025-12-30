#!/usr/bin/env pwsh
# =============================================================================
# Cloud Video Conversion System - Minikube Deployment Script
# =============================================================================

Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "Cloud Video Conversion System - Minikube Deployment" -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host ""

# Function to check command existence
function Test-Command {
    param([string]$Command)
    $null = Get-Command $Command -ErrorAction SilentlyContinue
    return $?
}

# [1/10] Check prerequisites
Write-Host "[1/10] Checking prerequisites..." -ForegroundColor Yellow

if (-not (Test-Command kubectl)) {
    Write-Host "ERROR: kubectl not found. Please install kubectl." -ForegroundColor Red
    exit 1
}

if (-not (Test-Command minikube)) {
    Write-Host "ERROR: minikube not found. Please install Minikube." -ForegroundColor Red
    exit 1
}

if (-not (Test-Command helm)) {
    Write-Host "ERROR: helm not found. Please install Helm." -ForegroundColor Red
    exit 1
}

Write-Host "   Prerequisites OK`n" -ForegroundColor Green

# [2/10] Clean up existing Minikube cluster
Write-Host "[2/10] Cleaning up existing Minikube cluster..." -ForegroundColor Yellow
minikube delete 2>$null
Write-Host "   Old cluster deleted`n" -ForegroundColor Green

# [3/10] Start fresh Minikube
Write-Host "[3/10] Starting fresh Minikube cluster..." -ForegroundColor Yellow
minikube start --driver=docker --cpus=4 --memory=8192 --disk-size=20g
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to start Minikube" -ForegroundColor Red
    exit 1
}
Write-Host "   Minikube started`n" -ForegroundColor Green

# [4/10] Connect to Minikube Docker daemon
Write-Host "[4/10] Connecting to Minikube Docker daemon..." -ForegroundColor Yellow
& minikube -p minikube docker-env --shell powershell | Invoke-Expression
Write-Host "   Connected to Minikube Docker`n" -ForegroundColor Green

# [5/10] Build Docker images
Write-Host "[5/10] Building Docker images..." -ForegroundColor Yellow
Write-Host "   Building API image..." -ForegroundColor Gray
docker build -t video-api:latest -f api/Dockerfile . | Out-Null
Write-Host "   Building Worker image..." -ForegroundColor Gray
docker build -t video-worker:latest -f worker/Dockerfile . | Out-Null  
Write-Host "   Building Frontend image..." -ForegroundColor Gray
docker build -t video-frontend:latest -f frontend/Dockerfile frontend/ | Out-Null
Write-Host "   Images built successfully`n" -ForegroundColor Green

# [6/10] Install KEDA
Write-Host "[6/10] Installing KEDA..." -ForegroundColor Yellow
helm repo add kedacore https://kedacore.github.io/charts 2>$null
helm repo update 2>$null | Out-Null
helm upgrade --install keda kedacore/keda --namespace keda --create-namespace --wait 2>$null | Out-Null
Write-Host "   KEDA installed`n" -ForegroundColor Green

# [7/10] Install Prometheus Stack
Write-Host "[7/10] Installing Prometheus + Grafana..." -ForegroundColor Yellow
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts 2>$null
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack `
    --namespace monitoring --create-namespace --wait `
    --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false `
    --set grafana.adminPassword=admin 2>$null | Out-Null
Write-Host "   Prometheus + Grafana installed`n" -ForegroundColor Green

# [8/10] Deploy application
Write-Host "[8/10] Deploying application..." -ForegroundColor Yellow
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/database-pvc.yaml
Write-Host "   Infrastructure configuration applied" -ForegroundColor Gray

kubectl apply -f k8s/rabbitmq.yaml
kubectl apply -f k8s/minio.yaml
Write-Host "   Waiting for RabbitMQ and MinIO..." -ForegroundColor Gray
kubectl wait --for=condition=ready pod -l app=rabbitmq -n video-processing --timeout=120s
kubectl wait --for=condition=ready pod -l app=minio -n video-processing --timeout=120s

kubectl apply -f k8s/minio.yaml  # Apply init job
Write-Host "   MinIO bucket initialization" -ForegroundColor Gray
Start-Sleep -Seconds 5

kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/worker-deployment.yaml
kubectl apply -f k8s/frontend-deployment.yaml
Write-Host "   Application services deployed" -ForegroundColor Gray

Write-Host "   Waiting for application pods..." -ForegroundColor Gray
kubectl wait --for=condition=ready pod -l app=api -n video-processing --timeout=120s
kubectl wait --for=condition=ready pod -l app=worker -n video-processing --timeout=120s
Write-Host "   Application deployed successfully`n" -ForegroundColor Green

# [9/10] Deploy KEDA ScaledObject
Write-Host "[9/10] Deploying KEDA autoscaler..." -ForegroundColor Yellow
kubectl apply -f k8s/keda-scaledobject.yaml
Write-Host "   Autoscaler configured`n" -ForegroundColor Green

# [10/10] Deploy monitoring
Write-Host "[10/10] Configuring monitoring..." -ForegroundColor Yellow
kubectl apply -f k8s/monitoring/servicemonitors.yaml 2>$null
Write-Host "   ServiceMonitors deployed`n" -ForegroundColor Green

# Show deployment status
Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "Deployment Status" -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan
kubectl get pods -n video-processing
Write-Host ""

Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "Access Points" -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Frontend UI:" -ForegroundColor Yellow
Write-Host "   minikube service frontend -n video-processing" -ForegroundColor White
Write-Host ""
Write-Host "API Swagger:" -ForegroundColor Yellow  
Write-Host "   minikube service api -n video-processing" -ForegroundColor White
Write-Host "   Then navigate to /docs" -ForegroundColor Gray
Write-Host ""
Write-Host "RabbitMQ Management:" -ForegroundColor Yellow
Write-Host "   kubectl port-forward svc/rabbitmq 15672:15672 -n video-processing" -ForegroundColor White
Write-Host "   http://localhost:15672 (guest/guest)" -ForegroundColor Gray
Write-Host ""
Write-Host "MinIO Console:" -ForegroundColor Yellow
Write-Host "   kubectl port-forward svc/minio 9001:9001 -n video-processing" -ForegroundColor White
Write-Host "   http://localhost:9001 (minioadmin/minioadmin)" -ForegroundColor Gray
Write-Host ""
Write-Host "Grafana Dashboard:" -ForegroundColor Yellow
Write-Host "   kubectl port-forward svc/prometheus-grafana 3000:80 -n monitoring" -ForegroundColor White
Write-Host "   http://localhost:3000 (admin/admin)" -ForegroundColor Gray
Write-Host ""
Write-Host "Prometheus:" -ForegroundColor Yellow
Write-Host "   kubectl port-forward svc/prometheus-kube-prometheus-prometheus 9090:9090 -n monitoring" -ForegroundColor White
Write-Host "   http://localhost:9090" -ForegroundColor Gray
Write-Host ""
Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "=========================================================" -ForegroundColor Cyan
