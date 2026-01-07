# Cloud Video Conversion System - Learning Guide for Beginners

**Author**: Your friendly AI assistant  
**Audience**: Students new to Kubernetes and distributed systems  
**Purpose**: Understand this demo project from the ground up

---

## Table of Contents

1. [The Big Picture - What Problem Are We Solving?](#1-the-big-picture)
2. [Core Concepts You Need to Know](#2-core-concepts)
3. [The Architecture - How It All Fits Together](#3-the-architecture)
4. [Walking Through the Components](#4-walking-through-components)
5. [How a Video Gets Processed (Step by Step)](#5-video-processing-flow)
6. [The Kubernetes Magic](#6-kubernetes-magic)
7. [Testing & Validation](#7-testing-validation)
8. [Common Questions & Troubleshooting](#8-qa)

---

## 1. The Big Picture - What Problem Are We Solving? {#1-the-big-picture}

### The Real-World Scenario

Imagine you're building YouTube. Users upload videos in **different formats** (MP4, AVI, MOV), but you need to:
- Convert them all to **one standard format** (MP4/H.264)
- Handle **bursts of traffic** (maybe 1000 uploads during lunch hour, then nothing for hours)
- **Never lose videos** even if servers crash
- **Only pay for servers when you need them**

This is what our Cloud Video Conversion System does!

### Why Traditional Servers Don't Work

❌ **Old Way (Static Servers)**:
- Buy 10 servers to handle peak load
- Servers sit **idle 80% of the time** → wasting money
- If one server crashes, videos get lost
- Can't handle sudden spikes (Black Friday, viral events)

✅ **Our Way (Cloud-Native with Kubernetes)**:
- Start with **0 workers** when idle
- Automatically scale to **10 workers** when busy
- If a worker crashes, the job gets **automatically retried**
- Only pay for what you use (scale to zero!)

---

## 2. Core Concepts You Need to Know {#2-core-concepts}

Before diving into the code, let's understand the building blocks:

### 2.1 What is Kubernetes (K8s)?

Think of Kubernetes as an **automatic robot manager** for your applications:

```
You say: "I need 5 copies of my video converter running"
Kubernetes: "Done! I'll start them, monitor them, restart them if they crash, 
             and spread them across servers for reliability."
```

**Key K8s Terms**:

| Term | Simple Explanation | Real-World Analogy |
|------|-------------------|-------------------|
| **Pod** | A running instance of your app | One worker in a factory |
| **Deployment** | Manages multiple pods | Factory manager who hires/fires workers based on demand |
| **Service** | A stable address to reach pods | The factory's front desk (always same phone number, even if workers change) |
| **PVC** | Persistent storage that survives crashes | A shared filing cabinet that doesn't disappear when workers leave |

### 2.2 Producer-Consumer Pattern

This is the **heart** of our architecture:

```
[Producer]  →  [Queue]  →  [Consumer]
  (API)         (RabbitMQ)   (Worker)
```

**How it works**:
1. **Producer (API)** receives video upload → puts a "job ticket" in the queue
2. **Queue (RabbitMQ)** stores job tickets safely (persists to disk)
3. **Consumer (Worker)** takes one ticket → converts the video → marks it done

**Why this is brilliant**:
- API responds **instantly** ("Thanks! Your video is queued")
- Workers process at their **own pace** (no rush, no crash)
- If a worker dies mid-job, RabbitMQ **re-queues the ticket** for another worker

### 2.3 Autoscaling - The Magic Trick

**Traditional Autoscaling (HPA - Horizontal Pod Autoscaler)**:
```
IF CPU > 80% THEN add more workers
```
❌ Problem: By the time CPU is high, you're **already overloaded**!

**Event-Driven Autoscaling (KEDA)**:
```
Workers needed = Queue depth ÷ 5

Queue: 0 messages  → 0 workers (save money!)
Queue: 25 messages → 5 workers
Queue: 100 messages → 10 workers (our max)
```
✅ **Proactive**: Scales **before** CPU melts, based on actual work waiting

---

## 3. The Architecture - How It All Fits Together {#3-the-architecture}

### 3.1 The Three Main Parts

```
┌─────────────────────────────────────────────────────────┐
│                  CLOUD VIDEO SYSTEM                     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐      ┌──────────────┐               │
│  │   Frontend   │      │   API (FastAPI)              │
│  │  (HTML/JS)   │─────▶│  - Generate URLs             │
│  └──────────────┘      │  - Track jobs                │
│                        └──────────────┘               │
│                              │                          │
│                              ▼                          │
│                        ┌──────────────┐                │
│                        │  RabbitMQ    │                │
│                        │  (Queue)     │                │
│                        └──────────────┘                │
│                              │                          │
│                              ▼                          │
│                        ┌──────────────┐                │
│                        │   Workers    │                │
│                        │  (0-10 pods) │                │
│                        │  - FFmpeg    │                │
│                        └──────────────┘                │
│                                                         │
│  ┌──────────────┐      ┌──────────────┐               │
│  │    MinIO     │      │   SQLite     │                │
│  │  (Storage)   │      │  (Database)  │                │
│  └──────────────┘      └──────────────┘               │
│                                                         │
│  ┌──────────────┐      ┌──────────────┐               │
│  │  Prometheus  │      │   Grafana    │                │
│  │  (Metrics)   │      │ (Dashboards) │                │
│  └──────────────┘      └──────────────┘               │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Component Responsibilities

| Component | What It Does | Why It's Important |
|-----------|--------------|-------------------|
| **Frontend** | Simple HTML page for uploading | User interface |
| **API Service** | - Generate presigned URLs<br>- Create jobs<br>- Return status | Lightweight coordinator (no video data passes through!) |
| **RabbitMQ** | Queue jobs, guarantee delivery | Ensures jobs aren't lost |
| **Workers** | Convert videos using FFmpeg | Does the heavy lifting |
| **MinIO** | Store input/output videos | Like AWS S3 but runs locally |
| **SQLite + PVC** | Store job status (PENDING/DONE) | Survives pod crashes |
| **KEDA** | Watch queue → adjust workers | Smart autoscaling |
| **Prometheus/Grafana** | Collect & visualize metrics | See what's happening in real-time |

---

## 4. Walking Through the Components {#4-walking-through-components}

Let's look at each piece in detail:

### 4.1 The API Service (`api/`)

**File**: `api/app.py`

**Key Endpoints**:

```python
POST /upload/request
# What: "I want to upload a video"
# Returns: { "job_id": "abc123", "presigned_url": "http://minio/..." }
# Why: Client gets a temporary URL to upload DIRECTLY to MinIO (not through API)

POST /jobs
# What: "I uploaded the video, now convert it!"
# Does: Creates DB entry (status=PENDING) → Publishes to RabbitMQ queue
# Returns: { "job_id": "abc123", "status": "PENDING" }

GET /jobs/{job_id}
# What: "Is my video done yet?"
# Returns: { "status": "PROCESSING" } or { "status": "DONE", "output_url": "..." }
```

**Smart Design - Presigned URLs**:

Instead of this (BAD):
```
User → Upload 500MB to API → API saves to MinIO
        (API becomes bottleneck!)
```

We do this (GOOD):
```
User → Ask API for upload URL
    → Upload 500MB DIRECTLY to MinIO
    → Tell API "I'm done uploading"
```

✅ API stays lightweight, handles only metadata!

### 4.2 The Worker Service (`worker/`)

**File**: `worker/app.py`

**What happens in a worker**:

```python
# 1. Connect to RabbitMQ
channel.basic_consume(queue='video_jobs', 
                      on_message_callback=process_job,
                      auto_ack=False)  # ← Manual ACK is KEY!

# 2. When a message arrives
def process_job(message):
    job_id = message['job_id']
    
    # Update status: PENDING → PROCESSING
    db.update(job_id, status='PROCESSING')
    
    # Download from MinIO
    input_file = minio.download(job_id)
    
    
    # Convert video (FFmpeg does heavy CPU work)
    output_file = ffmpeg.convert(input_file, format='mp4')
    
    # Upload result to MinIO
    minio.upload(output_file)
    
    # Update status: PROCESSING → DONE
    db.update(job_id, status='DONE')
    
    # Tell RabbitMQ: "I finished, remove this message"
    channel.basic_ack(message.delivery_tag)
```

**Critical - Manual Acknowledgement**:

```
Worker receives message → Message stays in queue (status: unacked)
Worker processes video → Success!
Worker sends ACK      → RabbitMQ deletes message

BUT IF WORKER CRASHES MID-PROCESS:
RabbitMQ detects disconnect → Re-queues message → Another worker picks it up!
```

✅ **Zero job loss** even if workers crash!

### 4.3 The Message Queue (RabbitMQ)

**Why a queue?**

Without a queue:
```
100 users upload at once → API tries to convert 100 videos → SERVER EXPLODES 💥
```

With a queue:
```
100 users upload → 100 jobs in queue → Workers process 5 at a time → Done in 20 waves
```

**RabbitMQ Configuration**:
```yaml
# k8s/rabbitmq-deployment.yaml
env:
  - name: RABBITMQ_DEFAULT_USER
    value: "guest"
  - name: RABBITMQ_DEFAULT_PASS
    value: "guest"
```

**Queue Properties**:
- **Durable**: Survives RabbitMQ restarts (saved to disk)
- **Manual ACK**: Messages aren't deleted until worker confirms success
- **Prefetch Count**: Each worker takes 1 message at a time (prevents hoarding)

### 4.4 The Storage Layers

#### MinIO (Object Storage)

Think of MinIO as "self-hosted AWS S3":

```
Buckets:
  └─ input/       ← Users upload raw videos here
  └─ output/      ← Workers save converted videos here
```

**Presigned URLs** (magic trick):
```python
# API generates a temporary URL (valid for 10 minutes)
url = minio.presigned_put_url('input/abc123.mp4', expires=600)

# Client uses this URL to upload directly
requests.put(url, data=video_file)
```

#### SQLite + PVC (Job Metadata)

**Why SQLite?**
- Simple (just a file: `database.db`)
- ACID transactions (no lost jobs)
- Good enough for demo (production would use PostgreSQL)

**Why PVC (Persistent Volume Claim)?**

Without PVC:
```
Pod writes to disk → Pod crashes → New pod starts → DATA LOST! 😱
```

With PVC:
```
Pod writes to PVC → Pod crashes → New pod mounts SAME PVC → DATA SAFE! ✅
```

**How it works in Kubernetes**:
```yaml
# k8s/api-deployment.yaml
volumeMounts:
  - name: database
    mountPath: /data  # SQLite file lives here

volumes:
  - name: database
    persistentVolumeClaim:
      claimName: database-pvc  # Shared disk!
```

### 4.5 The Autoscaler (KEDA)

**File**: `k8s/keda-scaledobject.yaml`

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: video-worker-scaler
spec:
  scaleTargetRef:
    name: video-worker  # Which deployment to scale
  
  minReplicaCount: 0    # Scale to ZERO when idle!
  maxReplicaCount: 10   # Never go above 10
  
  triggers:
    - type: rabbitmq
      metadata:
        queueName: video_jobs
        queueLength: "5"  # 1 worker per 5 messages
```

**How KEDA Decides**:

```
Current queue depth: 37 messages
Target: 5 messages per worker
Desired workers = ceil(37 / 5) = 8 workers

Current workers: 3
Action: Scale UP by 5 workers
```

**Scaling Timeline**:
```
t=0s:   Queue depth: 0   → Workers: 0 (idle, saving money!)
t=10s:  100 jobs arrive  → Workers: 0 (KEDA detects spike)
t=15s:  KEDA triggers    → Workers: 10 (scaling up...)
t=30s:  Pods ready       → Workers: 10 (processing!)
t=120s: Queue empty      → Workers: 10 (cooldown period)
t=150s: Cooldown ends    → Workers: 0 (scale down!)
```

---

## 5. How a Video Gets Processed (Step by Step) {#5-video-processing-flow}

Let's follow a video from upload to completion:

### Step 1: User Requests Upload

```http
POST /upload/request
{
  "filename": "vacation.mov",
  "content_type": "video/quicktime"
}
```

**API does**:
1. Generate unique `job_id` = `"abc123"`
2. Create presigned URL for MinIO: `http://minio/input/abc123.mov?signature=...`
3. Pre-insert job in DB: `status=PENDING`
4. Return to user

### Step 2: User Uploads Video

```javascript
// Frontend JavaScript
const response = await fetch(presigned_url, {
  method: 'PUT',
  body: videoFile,
  headers: { 'Content-Type': 'video/quicktime' }
});
```

**What happens**:
- Video goes **directly** to MinIO (NOT through API!)
- API is free to handle other requests
- MinIO saves file as `input/abc123.mov`

### Step 3: User Triggers Conversion

```http
POST /jobs
{
  "job_id": "abc123",
  "output_format": "mp4"
}
```

**API does**:
1. Publish message to RabbitMQ queue:
   ```json
   {
     "job_id": "abc123",
     "input_path": "input/abc123.mov",
     "output_format": "mp4"
   }
   ```
2. Return immediately: `{ "status": "PENDING" }`

### Step 4: KEDA Sees Work & Scales

```
KEDA checks queue every 30 seconds:
"Oh! 1 message in queue, but 0 workers. Let me start 1 worker..."
```

Kubernetes starts a worker pod:
```
t=0s: Pod created (status: Pending)
t=5s: Container image pulled
t=10s: Container started, worker connects to RabbitMQ
```

### Step 5: Worker Processes Job

```python
# Worker receives message
job = rabbitmq.consume()  # {"job_id": "abc123", ...}

# Update DB
db.execute("UPDATE jobs SET status='PROCESSING' WHERE id='abc123'")

# Download video
video_data = minio.get_object('input', 'abc123.mov')
with open('/tmp/input.mov', 'wb') as f:
    f.write(video_data)

# Convert video (this takes time!)
subprocess.run([
    'ffmpeg',
    '-i', '/tmp/input.mov',
    '-c:v', 'libx264',      # H.264 video codec
    '-crf', '23',           # Quality
    '-c:a', 'aac',          # AAC audio codec
    '/tmp/output.mp4'
])

# Upload result
minio.put_object('output', 'abc123.mp4', '/tmp/output.mp4')

# Update DB
db.execute("UPDATE jobs SET status='DONE', output_url='output/abc123.mp4' WHERE id='abc123'")

# Tell RabbitMQ "I'm done, delete the message"
rabbitmq.ack(job.delivery_tag)
```

### Step 6: User Checks Status

```http
GET /jobs/abc123

Response:
{
  "job_id": "abc123",
  "status": "DONE",
  "output_url": "http://minio/output/abc123.mp4"
}
```

User downloads the converted video! 🎉

---

## 6. Kubernetes Magic {#6-kubernetes-magic}

### 6.1 What Kubernetes Does for Us

Kubernetes is constantly running invisible tasks:

```
Every 10 seconds, Kubernetes checks:
✓ Are 5 worker pods supposed to be running?
✓ Are 5 worker pods ACTUALLY running?
  → If pod crashed: "Restarting pod #3..."
  → If node died: "Moving pod #2 to healthy node..."

KEDA adds:
✓ Check RabbitMQ queue depth: 25 messages
✓ Calculate: 25 / 5 = 5 workers needed
  → Currently have 2 workers
  → Action: "Starting 3 more pods..."
```

### 6.2 Key Kubernetes Files

| File | What It Does |
|------|--------------|
| `k8s/api-deployment.yaml` | How many API pods to run (usually 1-2) |
| `k8s/worker-deployment.yaml` | Worker pod template (KEDA controls count) |
| `k8s/rabbitmq-deployment.yaml` | RabbitMQ server |
| `k8s/minio-deployment.yaml` | MinIO storage server |
| `k8s/keda-scaledobject.yaml` | Autoscaling rules |
| `k8s/database-pvc.yaml` | Persistent disk for SQLite |

### 6.3 How to Deploy Everything

```bash
# 1. Start Minikube (local Kubernetes cluster)
minikube start --cpus=4 --memory=8192

# 2. Build Docker images INSIDE Minikube
eval $(minikube docker-env)
docker build -t video-api:latest ./api
docker build -t video-worker:latest ./worker

# 3. Apply ALL Kubernetes configs
kubectl apply -f k8s/

# 4. Watch pods come online
kubectl get pods -w

# Expected output:
# NAME                            READY   STATUS    
# video-api-xxx                   1/1     Running
# video-worker-xxx                0/0     Pending   (will start when queue has jobs)
# rabbitmq-xxx                    1/1     Running
# minio-xxx                       1/1     Running
```

### 6.4 Viewing Logs

```bash
# See what API is doing
kubectl logs -f deployment/video-api

# See what a worker is doing
kubectl logs -f deployment/video-worker

# Check RabbitMQ queue status
kubectl exec -it rabbitmq-xxx -- rabbitmqctl list_queues
```

---

## 7. Testing & Validation {#7-testing-validation}

### 7.1 Baseline Test (Does it work?)

**Goal**: Verify basic functionality

```bash
python scripts/simple-load-test.py \
  --api-url http://localhost:8000 \
  --num-jobs 10 \
  --video-file test_video_10mb.mp4
```

**What it tests**:
- ✓ Upload request works
- ✓ MinIO presigned URLs work
- ✓ Jobs get queued
- ✓ Workers process jobs
- ✓ Videos get converted
- ✓ Status updates correctly

**Expected results**:
- 10/10 jobs succeed (100% success rate)
- Average time: ~2-3 seconds per 10MB video

### 7.2 Scalability Test (Does it scale?)

**Goal**: Verify KEDA autoscaling

```bash
python scripts/load-generator.py \
  --api-url http://localhost:8000 \
  --num-jobs 100 \
  --concurrency 10
```

**What to observe**:

```bash
# Terminal 1: Watch workers scale
watch kubectl get pods

# Initial state:
# video-worker-xxx   0/0  → No workers (scaled to zero)

# After jobs submitted:
# t=10s:  video-worker-xxx-1   1/1   Running
# t=20s:  video-worker-xxx-2   1/1   Running
# t=30s:  video-worker-xxx-3   1/1   Running
# ...eventually...
# t=60s:  10 workers running (max reached)

# Terminal 2: Watch queue drain
kubectl exec -it rabbitmq-xxx -- rabbitmqctl list_queues

# video_jobs 100  ← Queue starts full
# video_jobs 75   ← Workers processing...
# video_jobs 45   
# video_jobs 10   
# video_jobs 0    ← All done!

# Terminal 3: After queue empty (wait 30s cooldown)
# video-worker pods scale back to 0
```

### 7.3 Fault Tolerance Test (Does it recover?)

**Test 1: Kill a worker mid-job**

```bash
# Find a worker processing a job
kubectl get pods | grep worker

# Kill it!
kubectl delete pod video-worker-abc123 --force

# What happens:
# 1. Worker dies mid-conversion
# 2. RabbitMQ detects disconnect (heartbeat timeout)
# 3. RabbitMQ re-queues the unacked message
# 4. Another worker picks it up
# 5. Video gets converted successfully!
```

✅ **Result**: Zero data loss!

**Test 2: Simulate network latency**

```bash
# Inject 500ms delay to MinIO traffic
python scripts/fault-tolerance-test.py --test network-latency

# What happens:
# - Jobs take longer (upload/download slow)
# - But all jobs eventually complete
# - No failures!
```

**Test 3: CPU stress**

```bash
# Stress worker CPU to 80%
python scripts/fault-tolerance-test.py --test cpu-stress

# What happens:
# - FFmpeg runs slower
# - Jobs take 2-3x longer
# - System remains stable
# - All jobs complete
```

### 7.4 Monitoring (What's happening?)

**Access Grafana**:

```bash
kubectl port-forward svc/grafana 3000:3000
# Open: http://localhost:3000
# Login: admin / admin
```

**Key Dashboards**:

1. **Scalability Dashboard**:
   - Green line: RabbitMQ queue depth
   - Yellow line: Number of worker pods
   - Watch them move together!

2. **Performance Dashboard**:
   - Job throughput (jobs/minute)
   - Latency percentiles (p50, p95, p99)
   - Resource usage (CPU, memory)

3. **Reliability Dashboard**:
   - Success rate (should be ~100%)
   - Error count (should be ~0)
   - Retry rate

---

## 8. Common Questions & Troubleshooting {#8-qa}

### Q1: Why scale to zero? Doesn't that add latency?

**A**: Yes, first job after scale-to-zero takes 30s extra (pod startup time).

**Trade-off**:
- ❌ Latency: First user waits 30s
- ✅ Cost: Save 100% of worker costs during idle (could be 12+ hours/day)

**For production**: Keep 1-2 "warm" workers (minReplicaCount: 2) for instant response.

### Q2: Why SQLite? Isn't that a "toy" database?

**A**: SQLite is actually very robust:
- ✅ ACID compliant (no data corruption)
- ✅ Handles 100,000s of reads/writes per second
- ✅ Used by Airbus (flight software!), Apple, Android

**Limitation**: Single writer (only 1 API pod can write at a time)

**For production**: Use PostgreSQL for multiple API replicas (high availability).

### Q3: What happens if RabbitMQ crashes?

**A**: 
- **Durable queues**: Messages saved to disk (survive crashes)
- **On restart**: RabbitMQ reloads messages from disk
- **Result**: Zero job loss!

**BUT**: RabbitMQ downtime = can't submit NEW jobs (workers keep processing existing queue).

**For production**: Run RabbitMQ cluster (3+ nodes) with replication.

### Q4: Why Minikube instead of real cloud?

**A**: Learning purposes!

| Minikube | Cloud (GKE/EKS/AKS) |
|----------|---------------------|
| Free | $$$ (pay per hour) |
| Runs on laptop | Requires credit card |
| Fast iteration | Deploy takes minutes |
| Good for demos | Production-ready |

**Same concepts**: Everything you learn on Minikube transfers to cloud!

### Q5: Worker stuck in "Pending" state?

**Troubleshoot**:

```bash
# Check why pod isn't starting
kubectl describe pod video-worker-xxx

# Common issues:
# 1. Image pull error → Build image: docker build -t video-worker:latest ./worker
# 2. No resources → Check: minikube status (need 4GB+ RAM)
# 3. PVC not bound → Check: kubectl get pvc
```

### Q6: Jobs stuck in "PENDING" forever?

**Troubleshoot**:

```bash
# 1. Is RabbitMQ running?
kubectl get pods | grep rabbitmq
kubectl logs rabbitmq-xxx

# 2. Are messages in queue?
kubectl exec -it rabbitmq-xxx -- rabbitmqctl list_queues

# 3. Are workers running?
kubectl get pods | grep worker
# If 0 workers: Check KEDA
kubectl logs -n keda deployment/keda-operator

# 4. Can workers connect to RabbitMQ?
kubectl logs deployment/video-worker
# Look for: "Connected to RabbitMQ successfully"
```

### Q7: How do I reset everything?

```bash
# Delete all resources
kubectl delete -f k8s/

# Clear PVCs (persistent data)
kubectl delete pvc --all

# Restart Minikube
minikube stop
minikube start --cpus=4 --memory=8192

# Re-deploy
kubectl apply -f k8s/
```

---

## Summary - Key Takeaways

When explaining this project to your class, emphasize these points:

### 1. **Architecture Pattern**
- Producer-Consumer decoupling via message queue
- API handles coordination, workers handle heavy lifting
- Autoscaling based on queue depth (not CPU)

### 2. **Reliability Mechanisms**
- Manual ACKs prevent job loss
- PVC ensures database survives crashes
- Durable queues persist messages to disk

### 3. **Cloud-Native Design**
- Stateless workers (can kill any time)
- Scale to zero (cost optimization)
- Kubernetes provides automatic recovery

### 4. **Real-World Applications**
- Video platforms (YouTube, TikTok)
- Image processing (Instagram filters)
- Document conversion (PDF generation)
- ML model inference (batch predictions)

### 5. **Minikube = Learning Platform**
- Same APIs as production Kubernetes
- Fast iteration (rebuild in seconds)
- Free and runs on laptop
- Transferable skills to AWS/GCP/Azure

---

## Next Steps for Learning

1. **Modify the Code**:
   - Change FFmpeg settings (resolution, bitrate)
   - Add email notifications when jobs complete
   - Support multiple output formats (MP4, WebM, AVI)

2. **Experiment with Scaling**:
   - Change `queueLength` to 10 (KEDA will scale differently)
   - Set `maxReplicaCount: 3` (see how it handles load)
   - Try `minReplicaCount: 2` (no cold starts!)

3. **Break Things on Purpose**:
   - Kill pods during processing (verify recovery)
   - Fill disk space (see error handling)
   - Simulate network failures (chaos engineering!)

4. **Explore Monitoring**:
   - Add custom Prometheus metrics
   - Create your own Grafana dashboard
   - Set up alerts (email when queue > 50)

---

**Good luck with your presentation! You've got this! 🚀**

*Questions? The code is your friend. Read `api/app.py` and `worker/app.py` - they're simpler than you think!*
