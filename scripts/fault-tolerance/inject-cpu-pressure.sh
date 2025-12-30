#!/bin/bash
# =============================================================================
# Fault Tolerance Demo: Inject CPU Pressure
# =============================================================================
# This script demonstrates system resilience under CPU resource pressure.
# Uses 'stress' or 'stress-ng' to consume CPU resources on worker pods.
#
# Expected Behavior:
# 1. Worker pod experiences high CPU usage
# 2. FFmpeg conversion slows down significantly
# 3. Kubernetes HPA may trigger scaling (if configured)
# 4. Jobs eventually complete (just slower)
# 5. No job failures or message loss
# =============================================================================

set -e

NAMESPACE="${NAMESPACE:-video-processing}"
CPU_WORKERS="${CPU_WORKERS:-2}"   # Number of CPU stress workers
DURATION="${DURATION:-60}"        # Duration in seconds

echo "=============================================="
echo "FAULT TOLERANCE DEMO: CPU Pressure Injection"
echo "=============================================="
echo ""
echo "Configuration:"
echo "  - CPU stress workers: ${CPU_WORKERS}"
echo "  - Duration: ${DURATION}s"
echo ""

# Pre-conditions check
echo "[1/6] Checking pre-conditions..."

if ! command -v kubectl &> /dev/null; then
    echo "ERROR: kubectl not found. Please install kubectl."
    exit 1
fi

# Find a worker pod
WORKER_POD=$(kubectl get pods -n "$NAMESPACE" -l "app=worker" --no-headers | head -1 | awk '{print $1}')
if [ -z "$WORKER_POD" ]; then
    echo "ERROR: No worker pods found."
    exit 1
fi

echo "   Target pod: $WORKER_POD"
echo ""

# Step 2: Check current resource usage
echo "[2/6] Current resource usage..."
kubectl top pod "$WORKER_POD" -n "$NAMESPACE" 2>/dev/null || echo "   (Metrics server not available)"
echo ""

# Step 3: Check if stress tool is available
echo "[3/6] Checking stress tool availability..."
STRESS_CMD=""
if kubectl exec "$WORKER_POD" -n "$NAMESPACE" -- which stress-ng &> /dev/null 2>&1; then
    STRESS_CMD="stress-ng"
elif kubectl exec "$WORKER_POD" -n "$NAMESPACE" -- which stress &> /dev/null 2>&1; then
    STRESS_CMD="stress"
else
    echo ""
    echo "   WARNING: Neither 'stress' nor 'stress-ng' found in container"
    echo ""
    echo "   To add stress tool, update Dockerfile with:"
    echo "   RUN apt-get update && apt-get install -y stress-ng"
    echo ""
    echo "   Alternative: Use a stress pod alongside the worker"
    echo ""
fi

# Step 4: Show current pods
echo "[4/6] Current worker pods:"
kubectl get pods -n "$NAMESPACE" -l "app=worker" -o wide
echo ""

# Step 5: Inject CPU pressure
echo "[5/6] Injecting CPU pressure..."
echo ""
echo "   Press ENTER to proceed or Ctrl+C to cancel..."
read -r

if [ -n "$STRESS_CMD" ]; then
    echo "   Starting $STRESS_CMD with $CPU_WORKERS CPU workers for ${DURATION}s..."
    kubectl exec "$WORKER_POD" -n "$NAMESPACE" -- \
        $STRESS_CMD --cpu "$CPU_WORKERS" --timeout "${DURATION}s" &
    STRESS_PID=$!
    
    echo ""
    echo "   Stress running in background (PID: $STRESS_PID)"
    echo "   Monitoring for ${DURATION} seconds..."
    echo ""
    
    # Monitor CPU during stress
    for i in $(seq 1 $((DURATION / 10))); do
        sleep 10
        echo "   [$((i * 10))s] CPU usage:"
        kubectl top pod "$WORKER_POD" -n "$NAMESPACE" 2>/dev/null || echo "   (Metrics not available)"
    done
    
    wait $STRESS_PID 2>/dev/null || true
    echo ""
    echo "   CPU pressure completed"
else
    echo "   Deploying stress pod as alternative..."
    cat << EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: cpu-stress-test
  namespace: $NAMESPACE
spec:
  containers:
  - name: stress
    image: progrium/stress
    command: ["stress"]
    args: ["--cpu", "$CPU_WORKERS", "--timeout", "${DURATION}s"]
    resources:
      requests:
        cpu: "500m"
      limits:
        cpu: "1000m"
  restartPolicy: Never
EOF
    
    echo "   Stress pod deployed. Waiting ${DURATION} seconds..."
    sleep "$DURATION"
    
    echo "   Cleaning up stress pod..."
    kubectl delete pod cpu-stress-test -n "$NAMESPACE" --ignore-not-found
fi

echo ""

# Step 6: Check results
echo "[6/6] Checking results..."
echo ""
echo "   Worker logs (last 10 lines):"
kubectl logs "$WORKER_POD" -n "$NAMESPACE" --tail=10
echo ""

echo "=============================================="
echo "VERIFICATION STEPS"
echo "=============================================="
echo ""
echo "1. Check Grafana for CPU-related impacts:"
echo "   - Conversion time should show spikes during stress"
echo "   - Throughput may temporarily decrease"
echo "   - Error rate should remain stable"
echo ""
echo "2. Check if KEDA/HPA scaled up workers:"
echo "   kubectl get pods -n $NAMESPACE -l app=worker"
echo "   kubectl get hpa -n $NAMESPACE"
echo ""
echo "3. Verify all jobs completed successfully:"
echo "   curl http://localhost:8000/jobs | jq '.[] | select(.status==\"failed\")'"
echo ""
echo "4. Check resource usage returned to normal:"
echo "   kubectl top pods -n $NAMESPACE"
echo ""
echo "=============================================="
echo "DEMO COMPLETE"
echo "=============================================="
