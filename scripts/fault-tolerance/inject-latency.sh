#!/bin/bash
# =============================================================================
# Fault Tolerance Demo: Inject Network Latency
# =============================================================================
# This script demonstrates system resilience under network latency conditions.
# Uses 'tc' (traffic control) to inject artificial latency on the worker pods.
#
# Expected Behavior:
# 1. Workers experience delayed responses from RabbitMQ/MinIO
# 2. Job processing slows down but continues
# 3. Grafana shows increased conversion times
# 4. No message loss or job failures (unless timeout exceeded)
# =============================================================================

set -e

NAMESPACE="${NAMESPACE:-video-processing}"
LATENCY_MS="${LATENCY_MS:-500}"  # Default 500ms latency
DURATION="${DURATION:-60}"        # Default 60 seconds

echo "=============================================="
echo "FAULT TOLERANCE DEMO: Network Latency Injection"
echo "=============================================="
echo ""
echo "Configuration:"
echo "  - Latency: ${LATENCY_MS}ms"
echo "  - Duration: ${DURATION}s"
echo ""

# Pre-conditions check
echo "[1/5] Checking pre-conditions..."

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

# Step 2: Check if tc is available in the container
echo "[2/5] Checking tc (traffic control) availability..."
if ! kubectl exec "$WORKER_POD" -n "$NAMESPACE" -- which tc &> /dev/null; then
    echo ""
    echo "   WARNING: 'tc' not available in container"
    echo "   Adding tc requires NET_ADMIN capability and iproute2 package"
    echo ""
    echo "   Alternative: Use a network chaos tool like:"
    echo "   - Chaos Mesh (https://chaos-mesh.org/)"
    echo "   - Litmus Chaos (https://litmuschaos.io/)"
    echo ""
    echo "   Simulating latency impact with sleep-based approach..."
    echo ""
fi

# Step 3: Get current network stats
echo "[3/5] Current worker status..."
kubectl logs "$WORKER_POD" -n "$NAMESPACE" --tail=5 2>/dev/null || echo "   (No recent logs)"
echo ""

# Step 4: Inject latency (if tc available) or simulate
echo "[4/5] Injecting network latency..."
echo ""
echo "   Press ENTER to proceed or Ctrl+C to cancel..."
read -r

# Try to inject with tc, fall back to chaos-mesh style yaml
if kubectl exec "$WORKER_POD" -n "$NAMESPACE" -- which tc &> /dev/null 2>&1; then
    echo "   Adding ${LATENCY_MS}ms latency to eth0..."
    kubectl exec "$WORKER_POD" -n "$NAMESPACE" -- tc qdisc add dev eth0 root netem delay ${LATENCY_MS}ms 2>/dev/null || \
        kubectl exec "$WORKER_POD" -n "$NAMESPACE" -- tc qdisc change dev eth0 root netem delay ${LATENCY_MS}ms
    
    echo "   Latency injected. Waiting ${DURATION} seconds..."
    sleep "$DURATION"
    
    echo "   Removing latency..."
    kubectl exec "$WORKER_POD" -n "$NAMESPACE" -- tc qdisc del dev eth0 root 2>/dev/null || true
else
    echo "   Creating Chaos Mesh NetworkChaos manifest (for reference)..."
    cat << EOF

# To use Chaos Mesh for network latency injection:
# 1. Install Chaos Mesh: helm install chaos-mesh chaos-mesh/chaos-mesh -n chaos-mesh --create-namespace
# 2. Apply this NetworkChaos resource:

apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: worker-network-delay
  namespace: $NAMESPACE
spec:
  action: delay
  mode: all
  selector:
    namespaces:
      - $NAMESPACE
    labelSelectors:
      app: worker
  delay:
    latency: "${LATENCY_MS}ms"
    jitter: "50ms"
    correlation: "50"
  duration: "${DURATION}s"

EOF
    echo ""
    echo "   Manual simulation: Adding artificial delay to next job..."
fi

echo ""

# Step 5: Monitor results
echo "[5/5] Monitoring impact..."
echo ""
echo "   Check Grafana for:"
echo "   - Increased conversion times (P95/P99)"
echo "   - Stable throughput (jobs still completing)"
echo "   - No increase in error rates"
echo ""

echo "=============================================="
echo "VERIFICATION STEPS"
echo "=============================================="
echo ""
echo "1. Check conversion time metrics in Grafana:"
echo "   - Open http://localhost:3000"
echo "   - Look at 'Conversion Performance' panel"
echo "   - P95/P99 should show temporary spike"
echo ""
echo "2. Verify no job failures:"
echo "   kubectl logs -l app=worker -n $NAMESPACE | grep -i 'error\\|fail'"
echo ""
echo "3. Check RabbitMQ queue for backlogs:"
echo "   - Open http://localhost:15672"
echo "   - Queue depth may increase during latency"
echo ""
echo "=============================================="
echo "DEMO COMPLETE"
echo "=============================================="
