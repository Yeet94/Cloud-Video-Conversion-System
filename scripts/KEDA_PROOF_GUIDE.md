# KEDA Autoscaling Proof Guide

## 🎯 Purpose
This guide shows you how to **prove KEDA is working** with visual, real-time evidence.

## 📋 Prerequisites

1. **Minikube running** with your deployment
2. **KEDA installed** in the cluster
3. **API service accessible** (via port-forward or Ingress)
4. **Python dependencies**:
   ```bash
   pip install requests colorama
   ```

## 🚀 Quick Start

### Step 1: Port-Forward the API (if needed)
```bash
kubectl port-forward svc/video-api 8000:8000
```

### Step 2: Run the Proof Script
```bash
cd scripts
python prove-keda-works.py --api-url http://localhost:8000 --num-jobs 50
```

## 📊 What the Script Does

### Phase 1: Initial State
- ✅ Checks current worker count (should be 0 or minReplicaCount)
- ✅ Checks queue depth (should be 0)
- ✅ Establishes baseline

### Phase 2: Job Submission
- ✅ Submits 50 jobs rapidly to create queue backlog
- ✅ Verifies jobs are queued in RabbitMQ

### Phase 3: Scale-Up Monitoring
- ✅ Watches KEDA scale workers UP
- ✅ Validates formula: `Workers = ceil(Queue / 5)`
- ✅ Shows real-time queue depth vs worker count

### Phase 4: Scale-Down Monitoring
- ✅ Watches queue drain as workers process jobs
- ✅ Watches KEDA scale workers DOWN after cooldown
- ✅ Verifies return to minimum replicas

### Phase 5: Summary & Validation
- ✅ Proves workers scaled up from queue
- ✅ Proves scaling followed KEDA formula
- ✅ Proves workers scaled down after completion
- ✅ Proves all jobs were processed

## 📈 Expected Output

```
================================================================================
                      PHASE 1: Initial State (Before Load)                      
================================================================================

[17:35:00] Initial Worker Count: 0
[17:35:00] Initial Queue Depth: 0

✓ Baseline established

================================================================================
                        PHASE 2: Submitting 50 Jobs                            
================================================================================

Submitting jobs rapidly to create queue backlog...

✓ Submitted 10/50 jobs
✓ Submitted 20/50 jobs
✓ Submitted 30/50 jobs
✓ Submitted 40/50 jobs
✓ Submitted 50/50 jobs

✓ Successfully submitted 50/50 jobs

[17:35:15] Queue Depth After Submission: 50
[17:35:15] Workers After Submission: 0

================================================================================
                      PHASE 3: Monitoring KEDA Scale-Up                        
================================================================================

Watching KEDA scale workers based on queue depth...
Formula: Workers = ceil(Queue / 5), Min=0, Max=10

[   0.0s] Queue:  50 | Workers:  0 | Expected: 10 | ↑
[   5.0s] Queue:  50 | Workers:  3 | Expected: 10 | ↑
  → KEDA scaled up to 3 workers!
[  10.0s] Queue:  48 | Workers:  7 | Expected: 10 | ↑
  → KEDA scaled up to 7 workers!
[  15.0s] Queue:  45 | Workers: 10 | Expected:  9 | ✓
  → KEDA scaled up to 10 workers!
  → Scale-up complete! Workers match expected count.
[  20.0s] Queue:  35 | Workers: 10 | Expected:  7 | ✓
[  25.0s] Queue:  20 | Workers: 10 | Expected:  4 | ✓
[  30.0s] Queue:   5 | Workers: 10 | Expected:  1 | ✓
[  35.0s] Queue:   0 | Workers: 10 | Expected:  0 | ↓
  → Queue drained!

================================================================================
                     PHASE 4: Monitoring KEDA Scale-Down                       
================================================================================

Queue is empty. Watching KEDA scale workers back down...
Note: KEDA has a cooldown period (typically 30-60s) before scaling down

[  40.0s] Queue:   0 | Workers: 10 | Expected:  0 | ↓
[  45.0s] Queue:   0 | Workers: 10 | Expected:  0 | ↓
[  50.0s] Queue:   0 | Workers:  8 | Expected:  0 | ↓
  → KEDA scaling down... (8 workers)
[  55.0s] Queue:   0 | Workers:  5 | Expected:  0 | ↓
  → KEDA scaling down... (5 workers)
[  60.0s] Queue:   0 | Workers:  2 | Expected:  0 | ↓
  → KEDA scaling down... (2 workers)
[  65.0s] Queue:   0 | Workers:  0 | Expected:  0 | ✓
  → Scale-down complete! Back to 0 workers after 65.0s

================================================================================
                           KEDA Proof Summary                                  
================================================================================

Initial State:
  Workers: 0
  Queue:   0

Peak State:
  Max Workers: 10
  Max Queue:   50

Final State:
  Workers: 0
  Queue:   0

KEDA Proof Validation:
  ✓ Workers scaled UP from queue backlog
  ✓ Scaling followed formula (expected ~10, got 10)
  ✓ Workers scaled DOWN after queue drain
  ✓ All jobs processed (queue empty)

================================================================================
                            KEDA IS WORKING! ✓                                 
================================================================================

Event log saved to: keda_proof_events.json
```

## 🔧 Advanced Usage

### Custom Job Count
```bash
# Test with 100 jobs (stress test)
python prove-keda-works.py --api-url http://localhost:8000 --num-jobs 100
```

### Custom KEDA Configuration
```bash
# If your KEDA config uses different values
python prove-keda-works.py \
  --api-url http://localhost:8000 \
  --target 10 \
  --min-workers 1 \
  --max-workers 5
```

### Different Namespace
```bash
python prove-keda-works.py \
  --api-url http://localhost:8000 \
  --namespace production
```

## 📁 Output Files

The script generates:
- **`keda_proof_events.json`**: Detailed event log with timestamps
  - Use this for analysis or graphing
  - Contains every monitoring checkpoint

## 🐛 Troubleshooting

### "kubectl not found"
**Solution**: Install kubectl and configure cluster access
```bash
minikube kubectl -- get pods
```

### "Cannot reach API"
**Solution**: Port-forward the service
```bash
kubectl port-forward svc/video-api 8000:8000
```

### "No workers scaling up"
**Possible causes**:
1. KEDA not installed: `kubectl get scaledobject`
2. ScaledObject misconfigured: `kubectl describe scaledobject`
3. RabbitMQ connection issue: `kubectl logs deployment/video-worker`

### "Workers not scaling down"
**This is normal!** KEDA has a cooldown period (30-60s) before scaling down to prevent thrashing.

## 📊 Viewing KEDA Configuration

Check your current KEDA setup:
```bash
# View ScaledObject
kubectl get scaledobject -o yaml

# View KEDA operator logs
kubectl logs -n keda deployment/keda-operator

# View current HPA (created by KEDA)
kubectl get hpa
```

## 🎓 Understanding the Proof

### Why This Proves KEDA Works

1. **Event-Driven Scaling**: Workers scale based on queue depth, NOT CPU
2. **Proactive**: Scaling happens BEFORE workers are overloaded
3. **Scale-to-Zero**: Workers disappear when idle (cost savings)
4. **Formula-Based**: Follows exact formula: `ceil(queue_depth / target)`

### Comparison to Traditional HPA

| Metric | Traditional HPA | KEDA (This Demo) |
|--------|----------------|------------------|
| **Trigger** | CPU > 80% | Queue depth > 0 |
| **Response Time** | Slow (reactive) | Fast (proactive) |
| **Scale to Zero** | ❌ No | ✅ Yes |
| **Bursty Workloads** | ❌ Poor | ✅ Excellent |

## 📸 Screenshots for Your Demo

The script produces **color-coded output** perfect for screenshots:
- 🟢 Green = Success/Expected state
- 🟡 Yellow = Scaling in progress
- 🔵 Cyan = Information
- 🔴 Red = Errors

## 🎬 Live Demo Tips

1. **Run in full-screen terminal** for maximum impact
2. **Point out the formula** in Phase 3
3. **Highlight the ✓ symbols** showing KEDA working
4. **Show the event log JSON** for detailed analysis
5. **Compare to your REPORT.md** Section 5.2 results

## 📚 Related Documentation

- Your project's `REPORT.md` Section 5.2 (Scalability)
- Your project's `LEARNING_GUIDE.md` Section 6.4 (Autoscaling)
- KEDA docs: https://keda.sh/docs/

---

**Ready to prove KEDA works?** Run the script and watch the magic happen! 🚀
