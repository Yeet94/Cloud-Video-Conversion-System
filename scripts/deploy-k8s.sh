#!/bin/bash
# =============================================================================
# Cloud Video Conversion System - Kubernetes Deployment Script
# =============================================================================
# This script deploys the complete video processing system to Docker Desktop
# Kubernetes cluster.
# =============================================================================

set -e

echo "================================================"
echo "Cloud Video Conversion System - K8s Deployment"
echo "================================================"
echo ""

# Check prerequisites
echo "[1/8] Checking prerequisites..."

if ! command -v kubectl &> /dev/null; then
    echo "ERROR: kubectl not found. Please install kubectl."
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo "ERROR: docker not found. Please install Docker Desktop."
    exit 1
fi

if ! command -v helm &> /dev/null; then
    echo "WARNING: Helm not found. KEDA and Prometheus will need manual installation."
    HELM_AVAILABLE=false
else
    HELM_AVAILABLE=true
fi

echo "   Prerequisites OK"
echo ""

# Build Docker images
echo "[2/8] Building Docker images..."
echo "   Building API image..."
docker build -t video-api:latest -f api/Dockerfile . > /dev/null

echo "   Building Worker image..."
docker build -t video-worker:latest -f worker/Dockerfile . > /dev/null

echo "   Images built successfully"
echo ""

# Create namespace
echo "[3/8] Creating namespace..."
kubectl apply -f k8s/namespace.yaml
echo ""

# Apply configuration
echo "[4/8] Applying configuration..."
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/database-pvc.yaml
echo ""

# Deploy infrastructure
echo "[5/8] Deploying infrastructure (RabbitMQ, MinIO)..."
kubectl apply -f k8s/rabbitmq.yaml
kubectl apply -f k8s/minio.yaml
echo "   Waiting for infrastructure to be ready..."
sleep 30
echo ""

# Deploy applications
echo "[6/8] Deploying applications (API, Worker)..."
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/worker-deployment.yaml
echo ""

# Install KEDA
echo "[7/8] Installing KEDA..."
if [ "$HELM_AVAILABLE" = true ]; then
    helm repo add kedacore https://kedacore.github.io/charts > /dev/null 2>&1 || true
    helm repo update > /dev/null 2>&1
    helm upgrade --install keda kedacore/keda -n keda --create-namespace > /dev/null 2>&1
    echo "   KEDA installed"
    sleep 10
    kubectl apply -f k8s/keda-scaledobject.yaml
else
    echo "   WARNING: Helm not available. Please install KEDA manually."
fi
echo ""

# Install Prometheus
echo "[8/8] Installing Prometheus Operator..."
if [ "$HELM_AVAILABLE" = true ]; then
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts > /dev/null 2>&1 || true
    helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
        -n monitoring --create-namespace > /dev/null 2>&1
    echo "   Prometheus Operator installed"
    kubectl apply -f k8s/monitoring/servicemonitors.yaml > /dev/null 2>&1 || true
else
    echo "   WARNING: Helm not available. Please install Prometheus manually."
fi
echo ""

# Show deployment status
echo "================================================"
echo "Deployment Status"
echo "================================================"
kubectl get pods -n video-processing
echo ""

echo "================================================"
echo "Access Points (after port-forward)"
echo "================================================"
echo ""
echo "API Service:"
echo "   kubectl port-forward svc/api 8000:8000 -n video-processing"
echo "   http://localhost:8000"
echo "   http://localhost:8000/docs"
echo ""
echo "RabbitMQ Management:"
echo "   kubectl port-forward svc/rabbitmq 15672:15672 -n video-processing"
echo "   http://localhost:15672 (guest/guest)"
echo ""
echo "MinIO Console:"
echo "   kubectl port-forward svc/minio 9001:9001 -n video-processing"
echo "   http://localhost:9001 (minioadmin/minioadmin)"
echo ""
echo "Grafana:"
echo "   kubectl port-forward svc/prometheus-grafana 3000:80 -n monitoring"
echo "   http://localhost:3000 (admin/prom-operator)"
echo ""
echo "================================================"
echo "Deployment Complete!"
echo "================================================"
