@echo off
REM =============================================================================
REM Cloud Video Conversion System - Kubernetes Deployment Script
REM =============================================================================
REM This script deploys the complete video processing system to Docker Desktop
REM Kubernetes cluster.
REM =============================================================================

echo ================================================
echo Cloud Video Conversion System - K8s Deployment
echo ================================================
echo.

REM Check prerequisites
echo [1/8] Checking prerequisites...
kubectl version --client >nul 2>&1
if errorlevel 1 (
    echo ERROR: kubectl not found. Please install kubectl.
    exit /b 1
)

docker version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker not running. Please start Docker Desktop.
    exit /b 1
)

helm version >nul 2>&1
if errorlevel 1 (
    echo WARNING: Helm not found. KEDA and Prometheus will need manual installation.
)

echo    Prerequisites OK
echo.

REM Build Docker images
echo [2/8] Building Docker images...
echo    Building API image...
docker build -t video-api:latest -f api/Dockerfile . >nul 2>&1
if errorlevel 1 (
    echo ERROR: Failed to build API image
    exit /b 1
)

echo    Building Worker image...
docker build -t video-worker:latest -f worker/Dockerfile . >nul 2>&1
if errorlevel 1 (
    echo ERROR: Failed to build Worker image
    exit /b 1
)
echo    Images built successfully
echo.

REM Create namespace
echo [3/8] Creating namespace...
kubectl apply -f k8s/namespace.yaml
echo.

REM Apply configuration
echo [4/8] Applying configuration...
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/database-pvc.yaml
echo.

REM Deploy infrastructure
echo [5/8] Deploying infrastructure (RabbitMQ, MinIO)...
kubectl apply -f k8s/rabbitmq.yaml
kubectl apply -f k8s/minio.yaml
echo    Waiting for infrastructure to be ready...
timeout /t 30 /nobreak >nul
echo.

REM Deploy applications
echo [6/8] Deploying applications (API, Worker)...
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/worker-deployment.yaml
echo.

REM Install KEDA
echo [7/8] Installing KEDA...
helm repo add kedacore https://kedacore.github.io/charts >nul 2>&1
helm repo update >nul 2>&1
helm upgrade --install keda kedacore/keda -n keda --create-namespace >nul 2>&1
if errorlevel 1 (
    echo    WARNING: KEDA installation failed. Please install manually.
) else (
    echo    KEDA installed
    timeout /t 10 /nobreak >nul
    kubectl apply -f k8s/keda-scaledobject.yaml
)
echo.

REM Install Prometheus (optional)
echo [8/8] Installing Prometheus Operator...
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >nul 2>&1
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack -n monitoring --create-namespace >nul 2>&1
if errorlevel 1 (
    echo    WARNING: Prometheus installation failed. Please install manually.
) else (
    echo    Prometheus Operator installed
    kubectl apply -f k8s/monitoring/servicemonitors.yaml >nul 2>&1
)
echo.

REM Show deployment status
echo ================================================
echo Deployment Status
echo ================================================
kubectl get pods -n video-processing
echo.

echo ================================================
echo Access Points (after port-forward)
echo ================================================
echo.
echo API Service:
echo    kubectl port-forward svc/api 8000:8000 -n video-processing
echo    http://localhost:8000
echo    http://localhost:8000/docs
echo.
echo RabbitMQ Management:
echo    kubectl port-forward svc/rabbitmq 15672:15672 -n video-processing
echo    http://localhost:15672 (guest/guest)
echo.
echo MinIO Console:
echo    kubectl port-forward svc/minio 9001:9001 -n video-processing
echo    http://localhost:9001 (minioadmin/minioadmin)
echo.
echo Grafana:
echo    kubectl port-forward svc/prometheus-grafana 3000:80 -n monitoring
echo    http://localhost:3000 (admin/prom-operator)
echo.
echo ================================================
echo Deployment Complete!
echo ================================================
