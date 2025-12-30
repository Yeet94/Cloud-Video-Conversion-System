#!/bin/bash
# =============================================================================
# Fault Tolerance Demo: Kill Worker Pod During Processing
# =============================================================================
# This script demonstrates that when a worker pod is killed during video
# processing, the job is re-queued and completed by another pod.
#
# Expected Behavior:
# 1. The killed pod's job is NACKed (not acknowledged)
# 2. RabbitMQ re-queues the message
# 3. Another worker pod picks up the job
# 4. The job completes successfully
# =============================================================================

set -e

NAMESPACE="${NAMESPACE:-video-processing}"
LABEL_SELECTOR="app=worker"

echo "=============================================="
echo "FAULT TOLERANCE DEMO: Kill Worker Pod"
echo "=============================================="
echo ""

# Pre-conditions check
echo "[1/5] Checking pre-conditions..."

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "ERROR: kubectl not found. Please install kubectl."
    exit 1
fi

# Check if namespace exists
if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
    echo "ERROR: Namespace '$NAMESPACE' not found."
    echo "Please deploy the application first."
    exit 1
fi

# Check worker pods
WORKER_PODS=$(kubectl get pods -n "$NAMESPACE" -l "$LABEL_SELECTOR" --no-headers 2>/dev/null | wc -l)
if [ "$WORKER_PODS" -lt 1 ]; then
    echo "ERROR: No worker pods found."
    exit 1
fi

echo "   Found $WORKER_PODS worker pod(s)"
echo ""

# Step 2: Show current state
echo "[2/5] Current worker pods:"
kubectl get pods -n "$NAMESPACE" -l "$LABEL_SELECTOR" -o wide
echo ""

# Step 3: Find a worker pod to kill
echo "[3/5] Selecting worker pod to terminate..."
TARGET_POD=$(kubectl get pods -n "$NAMESPACE" -l "$LABEL_SELECTOR" --no-headers | head -1 | awk '{print $1}')
echo "   Target pod: $TARGET_POD"
echo ""

# Optional: Check if the pod is processing a job
echo "[4/5] Checking pod logs for active processing..."
kubectl logs "$TARGET_POD" -n "$NAMESPACE" --tail=5 2>/dev/null || echo "   (No recent logs)"
echo ""

# Step 5: Kill the pod
echo "[5/5] Killing worker pod: $TARGET_POD"
echo ""
echo "   Press ENTER to proceed or Ctrl+C to cancel..."
read -r

# Delete the pod
echo "   Deleting pod..."
kubectl delete pod "$TARGET_POD" -n "$NAMESPACE" --grace-period=0 --force

echo ""
echo "=============================================="
echo "VERIFICATION STEPS"
echo "=============================================="
echo ""
echo "1. Watch pods recover:"
echo "   kubectl get pods -n $NAMESPACE -l $LABEL_SELECTOR -w"
echo ""
echo "2. Check RabbitMQ queue for re-queued messages:"
echo "   - Open RabbitMQ Management: http://localhost:15672"
echo "   - Check 'video-jobs' queue"
echo ""
echo "3. Check Grafana for pod failure event:"
echo "   - Open Grafana: http://localhost:3000"
echo "   - Look at 'Worker Pods' metric"
echo ""
echo "4. Verify job completion in API:"
echo "   curl http://localhost:8000/jobs"
echo ""
echo "=============================================="
echo "DEMO COMPLETE"
echo "=============================================="
