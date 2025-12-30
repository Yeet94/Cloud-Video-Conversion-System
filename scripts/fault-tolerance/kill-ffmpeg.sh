#!/bin/bash
# =============================================================================
# Fault Tolerance Demo: Kill FFmpeg Process Inside Worker
# =============================================================================
# This script demonstrates that when FFmpeg crashes inside a worker container,
# the worker detects the failure, NACKs the message, and RabbitMQ re-queues
# the job for another worker to process.
#
# Expected Behavior:
# 1. FFmpeg process is terminated mid-conversion
# 2. Worker detects FFmpeg failure (non-zero exit code)
# 3. Worker NACKs the message, causing RabbitMQ to re-queue
# 4. Same or different worker retries the job
# 5. Job eventually completes successfully
# =============================================================================

set -e

NAMESPACE="${NAMESPACE:-video-processing}"
LABEL_SELECTOR="app=worker"

echo "=============================================="
echo "FAULT TOLERANCE DEMO: Kill FFmpeg Process"
echo "=============================================="
echo ""

# Pre-conditions check
echo "[1/5] Checking pre-conditions..."

if ! command -v kubectl &> /dev/null; then
    echo "ERROR: kubectl not found. Please install kubectl."
    exit 1
fi

WORKER_PODS=$(kubectl get pods -n "$NAMESPACE" -l "$LABEL_SELECTOR" --no-headers 2>/dev/null | wc -l)
if [ "$WORKER_PODS" -lt 1 ]; then
    echo "ERROR: No worker pods found."
    exit 1
fi

echo "   Found $WORKER_PODS worker pod(s)"
echo ""

# Step 2: Select target pod
echo "[2/5] Current worker pods:"
kubectl get pods -n "$NAMESPACE" -l "$LABEL_SELECTOR"
echo ""

TARGET_POD=$(kubectl get pods -n "$NAMESPACE" -l "$LABEL_SELECTOR" --no-headers | head -1 | awk '{print $1}')
echo "   Target pod: $TARGET_POD"
echo ""

# Step 3: Check for running FFmpeg processes
echo "[3/5] Checking for running FFmpeg processes..."
FFMPEG_PID=$(kubectl exec "$TARGET_POD" -n "$NAMESPACE" -- pgrep ffmpeg 2>/dev/null || echo "")

if [ -z "$FFMPEG_PID" ]; then
    echo ""
    echo "   No FFmpeg process currently running in $TARGET_POD"
    echo "   Please submit some video conversion jobs first, then run this script again."
    echo ""
    echo "   To submit a job:"
    echo "   curl -X POST http://localhost:8000/jobs \\"
    echo "     -H 'Content-Type: application/json' \\"
    echo "     -d '{\"input_path\": \"uploads/sample.mp4\", \"output_format\": \"mp4\"}'"
    echo ""
    exit 1
fi

echo "   Found FFmpeg process (PID: $FFMPEG_PID)"
echo ""

# Step 4: Kill FFmpeg
echo "[4/5] Killing FFmpeg process..."
echo ""
echo "   Press ENTER to proceed or Ctrl+C to cancel..."
read -r

echo "   Sending SIGKILL to FFmpeg (PID: $FFMPEG_PID)..."
kubectl exec "$TARGET_POD" -n "$NAMESPACE" -- kill -9 "$FFMPEG_PID" 2>/dev/null || echo "   Process may have already exited"

echo ""

# Step 5: Monitor results
echo "[5/5] Monitoring worker response..."
echo ""
echo "   Waiting 5 seconds for worker to handle failure..."
sleep 5

echo ""
echo "   Worker logs (last 20 lines):"
kubectl logs "$TARGET_POD" -n "$NAMESPACE" --tail=20

echo ""
echo "=============================================="
echo "VERIFICATION STEPS"
echo "=============================================="
echo ""
echo "1. Check worker logs for error handling:"
echo "   kubectl logs $TARGET_POD -n $NAMESPACE | grep -i 'error\\|fail\\|nack'"
echo ""
echo "2. Check RabbitMQ for re-queued message:"
echo "   - Open RabbitMQ Management: http://localhost:15672"
echo "   - Check 'video-jobs' queue 'Ready' count"
echo ""
echo "3. Check Grafana for failure spike:"
echo "   - Open Grafana: http://localhost:3000"
echo "   - Look at 'Error Rates' panel"
echo ""
echo "4. Monitor job retry:"
echo "   kubectl logs -f -l $LABEL_SELECTOR -n $NAMESPACE | grep -i 'processing\\|completed'"
echo ""
echo "=============================================="
echo "DEMO COMPLETE"
echo "=============================================="
