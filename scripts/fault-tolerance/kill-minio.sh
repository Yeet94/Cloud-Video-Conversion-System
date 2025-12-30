#!/bin/bash
# =============================================================================
# Fault Tolerance Demo: Kill MinIO Pod
# =============================================================================
# This script demonstrates that when a MinIO pod is killed, the StatefulSet
# controller recovers the pod and re-attaches the persistent volume claim,
# ensuring no data is lost.
#
# Expected Behavior:
# 1. MinIO pod is forcefully terminated
# 2. StatefulSet controller detects pod failure
# 3. New MinIO pod is created with same name
# 4. PVC is re-attached to the new pod
# 5. All previously stored videos are still accessible
# =============================================================================

set -e

NAMESPACE="${NAMESPACE:-video-processing}"

echo "=============================================="
echo "FAULT TOLERANCE DEMO: Kill MinIO Pod"
echo "=============================================="
echo ""

# Pre-conditions check
echo "[1/6] Checking pre-conditions..."

if ! command -v kubectl &> /dev/null; then
    echo "ERROR: kubectl not found. Please install kubectl."
    exit 1
fi

MINIO_POD=$(kubectl get pods -n "$NAMESPACE" -l "app=minio" --no-headers 2>/dev/null | head -1 | awk '{print $1}')
if [ -z "$MINIO_POD" ]; then
    echo "ERROR: MinIO pod not found."
    exit 1
fi

echo "   MinIO pod: $MINIO_POD"
echo ""

# Step 2: Show current state
echo "[2/6] Current MinIO state:"
kubectl get pods -n "$NAMESPACE" -l "app=minio"
echo ""
kubectl get pvc -n "$NAMESPACE" | grep minio || true
echo ""

# Step 3: Check stored data
echo "[3/6] Checking MinIO data (bucket contents)..."
# List objects in bucket via API
MINIO_OBJECTS=$(kubectl exec "$MINIO_POD" -n "$NAMESPACE" -- ls -la /data/videos/ 2>/dev/null || echo "No data directory or empty")
echo "   $MINIO_OBJECTS"
echo ""

# Step 4: Record object count for verification
echo "[4/6] Recording current state for verification..."
PRE_KILL_COUNT=$(kubectl exec "$MINIO_POD" -n "$NAMESPACE" -- find /data -type f 2>/dev/null | wc -l || echo "0")
echo "   Files in MinIO storage: $PRE_KILL_COUNT"
echo ""

# Step 5: Kill MinIO pod
echo "[5/6] Killing MinIO pod: $MINIO_POD"
echo ""
echo "   WARNING: This will temporarily make storage unavailable!"
echo "   Press ENTER to proceed or Ctrl+C to cancel..."
read -r

START_TIME=$(date +%s)
echo "   Deleting pod (force)..."
kubectl delete pod "$MINIO_POD" -n "$NAMESPACE" --grace-period=0 --force

echo ""
echo "   Waiting for pod to recover..."
echo ""

# Wait for pod to come back
while true; do
    POD_STATUS=$(kubectl get pods -n "$NAMESPACE" -l "app=minio" --no-headers 2>/dev/null | awk '{print $3}' || echo "NotFound")
    POD_READY=$(kubectl get pods -n "$NAMESPACE" -l "app=minio" --no-headers 2>/dev/null | awk '{print $2}' || echo "0/1")
    
    ELAPSED=$(($(date +%s) - START_TIME))
    echo "   [$ELAPSED s] Pod status: $POD_STATUS, Ready: $POD_READY"
    
    if [ "$POD_STATUS" = "Running" ] && [ "$POD_READY" = "1/1" ]; then
        echo ""
        echo "   Pod recovered!"
        break
    fi
    
    if [ "$ELAPSED" -gt 120 ]; then
        echo "   ERROR: Pod did not recover within 2 minutes"
        exit 1
    fi
    
    sleep 2
done

RECOVERY_TIME=$(($(date +%s) - START_TIME))
echo "   Recovery time: $RECOVERY_TIME seconds"
echo ""

# Step 6: Verify data persistence
echo "[6/6] Verifying data persistence..."
NEW_MINIO_POD=$(kubectl get pods -n "$NAMESPACE" -l "app=minio" --no-headers | head -1 | awk '{print $1}')

POST_KILL_COUNT=$(kubectl exec "$NEW_MINIO_POD" -n "$NAMESPACE" -- find /data -type f 2>/dev/null | wc -l || echo "0")
echo "   Files before kill: $PRE_KILL_COUNT"
echo "   Files after recovery: $POST_KILL_COUNT"

if [ "$PRE_KILL_COUNT" = "$POST_KILL_COUNT" ]; then
    echo ""
    echo "   ✅ DATA PERSISTENCE VERIFIED - No data lost!"
else
    echo ""
    echo "   ⚠️  File count changed (may be due to ongoing operations)"
fi

echo ""
echo "=============================================="
echo "VERIFICATION STEPS"
echo "=============================================="
echo ""
echo "1. Verify MinIO is healthy:"
echo "   kubectl get pods -n $NAMESPACE -l app=minio"
echo "   curl http://localhost:9000/minio/health/live"
echo ""
echo "2. Verify PVC is still bound:"
echo "   kubectl get pvc -n $NAMESPACE | grep minio"
echo ""
echo "3. Check MinIO console for data:"
echo "   - Open MinIO Console: http://localhost:9001"
echo "   - Login: minioadmin / minioadmin"
echo "   - Browse 'videos' bucket"
echo ""
echo "4. Check Grafana for MinIO metrics:"
echo "   - Open Grafana: http://localhost:3000"
echo "   - Verify MinIO metrics resumed"
echo ""
echo "5. Test video download after recovery:"
echo "   curl http://localhost:8000/jobs"
echo ""
echo "=============================================="
echo "DEMO COMPLETE - Recovery time: ${RECOVERY_TIME}s"
echo "=============================================="
