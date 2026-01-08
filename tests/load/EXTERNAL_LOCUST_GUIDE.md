# Locust External Load Testing Guide

This guide explains how to run Locust **externally** (on your local machine) to test the Kubernetes deployment.

---

## Why External Locust?

**Problem with Internal Locust (in Kubernetes):**
- Presigned URLs use `localhost` which doesn't resolve correctly from inside pods
- Complex networking issues with MinIO uploads

**Solution - External Locust:**
- ✅ Runs on your local machine (outside Kubernetes)
- ✅ Uses `/load-test/generate` endpoint (no file uploads needed)
- ✅ Accesses API via `http://localhost/api` (Minikube tunnel)
- ✅ Simple, reliable, works perfectly

---

## Prerequisites

1. **Minikube tunnel running:**
   ```powershell
   minikube tunnel
   ```

2. **Install Locust:**
   ```powershell
   pip install locust
   ```

---

## Quick Start

### **1. Navigate to tests directory:**
```powershell
cd "c:\Users\Hcche\Downloads\Cloud Video Conversion System\tests\load"
```

### **2. Run Locust:**
```powershell
locust -f locustfile-external.py --host=http://localhost/api
```

### **3. Open Web UI:**
```
http://localhost:8089
```

### **4. Configure test:**
- **Number of users:** 10 (start small)
- **Spawn rate:** 2 users/second
- **Host:** http://localhost/api (pre-filled)
- Click **Start swarming**

---

## Test Scenarios

### **Scenario 1: Normal Load**
```powershell
locust -f locustfile-external.py --host=http://localhost/api --users 10 --spawn-rate 2
```
- **Users:** 10 concurrent users
- **Spawn rate:** 2 users/second
- **Duration:** Run until you stop it
- **Expected:** Workers scale 1 → 3-5 pods

### **Scenario 2: Burst Traffic**
```powershell
locust -f locustfile-external.py --host=http://localhost/api --users 20 --spawn-rate 5 --run-time 2m
```
- **Users:** 20 concurrent users
- **Spawn rate:** 5 users/second
- **Duration:** 2 minutes
- **Expected:** Workers scale to max (10 pods)

### **Scenario 3: Headless Mode (No UI)**
```powershell
locust -f locustfile-external.py --host=http://localhost/api --users 15 --spawn-rate 3 --run-time 5m --headless --html report.html
```
- Runs without web UI
- Generates HTML report at the end
- Good for automated testing

---

## What Gets Tested

### **VideoProcessingUser (Normal User):**
- **Task 1 (weight 10):** Generate test video + Create job
- **Task 2 (weight 5):** Check job status (polling)
- **Task 3 (weight 3):** List all jobs
- **Task 4 (weight 2):** Get download URL for completed job
- **Task 5 (weight 1):** Health check

### **BurstUser (Stress Test):**
- Rapidly creates jobs (0.1-0.5s wait time)
- Tests autoscaling behavior
- Use with: `--user-classes BurstUser`

---

## Monitoring During Test

### **1. Watch Grafana Dashboard:**
```
http://localhost/grafana
```
- Navigate to "Video Processing - Comprehensive Dashboard"
- Watch: Throughput, Queue Depth, Worker Pods, CPU usage

### **2. Watch Pods Scaling:**
```powershell
kubectl get pods -n video-processing -w
```

### **3. Watch KEDA Scaling:**
```powershell
kubectl get scaledobject -n video-processing -w
```

### **4. Watch Queue Depth:**
```powershell
kubectl exec -n video-processing rabbitmq-0 -- rabbitmqctl list_queues
```

---

## Locust Web UI Features

### **Statistics Tab:**
- Request counts, failures, response times
- Percentiles (P50, P95, P99)
- Requests per second

### **Charts Tab:**
- Real-time graphs
- Total requests per second
- Response times
- Number of users

### **Failures Tab:**
- Failed requests with error messages
- Helps debug issues

### **Download Data:**
- Download stats as CSV
- Download exceptions
- Generate HTML report

---

## Example Test Flow

```powershell
# 1. Start Minikube tunnel (if not running)
minikube tunnel

# 2. Open Grafana in browser
start http://localhost/grafana

# 3. Run Locust
cd "tests\load"
locust -f locustfile-external.py --host=http://localhost/api

# 4. Open Locust UI
start http://localhost:8089

# 5. Configure:
#    - Users: 15
#    - Spawn rate: 3
#    - Click "Start swarming"

# 6. Watch in Grafana:
#    - Queue depth increases
#    - Workers scale up (1 → 5 → 10)
#    - Throughput increases
#    - Jobs complete

# 7. Stop test after 5 minutes
#    - Click "Stop" in Locust UI
#    - Download report

# 8. Watch workers scale down
#    - Queue empties
#    - Workers scale down (10 → 5 → 1)
```

---

## Troubleshooting

### **Issue: Connection refused**
```
Error: ConnectionError: HTTPConnectionPool(host='localhost', port=80)
```
**Solution:** Make sure `minikube tunnel` is running

### **Issue: 404 Not Found**
```
Error: 404 Client Error: Not Found for url: http://localhost/api/load-test/generate
```
**Solution:** API not deployed or endpoint doesn't exist. Rebuild API:
```powershell
docker build -t video-api:latest -f api/Dockerfile .
kubectl rollout restart deployment/api -n video-processing
```

### **Issue: Jobs failing**
```
Error: Failed to create job
```
**Solution:** Check API logs:
```powershell
kubectl logs -n video-processing deployment/api --tail=50
```

---

## Comparison: External vs Internal Locust

| Feature | External (This Guide) | Internal (K8s) |
|---------|----------------------|----------------|
| **Setup** | ✅ Simple - just `pip install locust` | ❌ Complex - Docker, K8s manifests |
| **Presigned URLs** | ✅ Works perfectly | ❌ Fails with localhost |
| **File Uploads** | ✅ Uses /load-test/generate | ❌ Needs actual video files |
| **Networking** | ✅ Via Minikube tunnel | ❌ Complex pod networking |
| **Best For** | **Demos, local testing** | Distributed load (100+ users) |

---

## Advanced: Custom User Classes

Run only burst users:
```powershell
locust -f locustfile-external.py --host=http://localhost/api --user-classes BurstUser --users 50 --spawn-rate 10
```

Run both user types with custom ratio:
```powershell
# 80% normal users, 20% burst users
locust -f locustfile-external.py --host=http://localhost/api --users 25 --spawn-rate 5
```

---

## Tips for Demo

1. **Start Grafana first** - Open dashboard before test
2. **Use moderate load** - 10-15 users is enough to show scaling
3. **Explain what's happening:**
   - "I'm simulating 15 concurrent users uploading videos"
   - "Watch the queue depth increase"
   - "KEDA detects the load and scales workers"
   - "Throughput increases as more workers come online"
4. **Show Locust UI** - Real-time stats are impressive
5. **Let it run 3-5 minutes** - Enough to see full scaling cycle

---

## Next Steps

- ✅ Run a test with 10 users
- ✅ Watch Grafana dashboard
- ✅ Observe worker scaling
- ✅ Generate HTML report
- ✅ Use for your demo!

**Locust is now ready for external testing!** 🚀
