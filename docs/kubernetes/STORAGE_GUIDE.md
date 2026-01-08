# Kubernetes Storage Guide - Understanding PVCs and Persistence

This guide explains how persistent storage works in the Cloud Video Conversion System, covering PVCs, volume mounting, and the SQLite limitation.

---

## Table of Contents

1. [Storage Overview](#storage-overview)
2. [Understanding PVCs](#understanding-pvcs)
3. [Volume Mounting Explained](#volume-mounting-explained)
4. [SQLite Multi-Writer Limitation](#sqlite-multi-writer-limitation)
5. [Viewing Your Data](#viewing-your-data)
6. [Common Questions](#common-questions)

---

## Storage Overview

### **3 Persistent Volume Claims (PVCs)**

Your system uses 3 separate PVCs for different purposes:

| PVC Name | Used By | Purpose | Size | Access Mode | What's Stored |
|----------|---------|---------|------|-------------|---------------|
| **database-pvc** | API + Workers | Job metadata | 1Gi | RWX | SQLite database (`jobs.db`) |
| **minio-pvc** | MinIO | Video files | 10Gi | RWO | Uploaded & converted videos |
| **rabbitmq-data-rabbitmq-0** | RabbitMQ | Message queue | 1Gi | RWO | Queue persistence data |

### **Check PVC Status**

```bash
# View all PVCs
kubectl get pvc -n video-processing

# Expected output:
# NAME                       STATUS   VOLUME        CAPACITY   ACCESS MODES
# database-pvc               Bound    pvc-xxxxx     1Gi        RWX
# minio-pvc                  Bound    pvc-xxxxx     10Gi       RWO
# rabbitmq-data-rabbitmq-0   Bound    pvc-xxxxx     1Gi        RWO
```

**Status: Bound** ✅ means the PVC is successfully connected to a persistent volume.

---

## Understanding PVCs

### **What is a PVC?**

**PVC (PersistentVolumeClaim) = Request for Storage**

Think of it like:
- **PVC** = "I need 10Gi of disk space"
- **PV (PersistentVolume)** = The actual storage Kubernetes provisions
- **StorageClass** = How/where to create the storage (in Minikube: local disk)

### **Access Modes Explained**

#### **RWX (ReadWriteMany)** - `database-pvc`
- ✅ **Multiple pods can mount and read/write** simultaneously
- Used by: API pod + Worker pods (1-10 replicas)
- **Why?** Both API and workers need to access the same `jobs.db` file
- ⚠️ **Limitation:** SQLite doesn't handle concurrent writes well (see below)

#### **RWO (ReadWriteOnce)** - `minio-pvc` & `rabbitmq-data`
- ✅ **Only ONE pod can mount** at a time
- Used by: Single MinIO pod, Single RabbitMQ pod
- **Why?** These services run as single instances with internal concurrency handling

### **PVCs vs Application Storage**

**Important:** The PVC doesn't determine WHAT you store - the application does!

```
┌─────────────────────────────────────────┐
│  PVC = Dumb Storage (Just Disk Space)   │
│  - Doesn't care about file types        │
│  - Could store SQLite, videos, text     │
└─────────────────────────────────────────┘
                   ▲
                   │
┌─────────────────────────────────────────┐
│  Application = Decides What to Store    │
│  - API uses SQLite library              │
│  - MinIO stores video files             │
│  - RabbitMQ uses Mnesia database        │
└─────────────────────────────────────────┘
```

**Example:**
- `database-pvc` doesn't "use SQLite"
- The **API/Worker Python code** uses SQLite
- SQLite creates `jobs.db` file on the PVC

---

## Volume Mounting Explained

### **What Does "Mounted" Mean?**

**Mounting = Attaching external storage to a directory path inside a container**

**Analogy:**
- **Your PC:** USB drive appears as `D:\` (mounted at D:)
- **Kubernetes:** PVC appears as `/data` (mounted at /data)

### **How Mounting Works**

#### **Example: MinIO Configuration**

```yaml
# From k8s/minio.yaml
containers:
  - name: minio
    volumeMounts:              # ← Where to attach storage
      - name: minio-data       # ← Reference to volume below
        mountPath: /data       # ← Directory inside container

volumes:                       # ← What storage to use
  - name: minio-data
    persistentVolumeClaim:
      claimName: minio-pvc     # ← Which PVC to attach
```

#### **What Happens:**

**Before Mounting:**
```
MinIO Container:
/
├── bin/
├── etc/
└── data/  ← Empty directory
```

**After Mounting minio-pvc to /data:**
```
MinIO Container:
/
├── bin/
├── etc/
└── data/  ← Now shows minio-pvc contents!
    └── videos/
        ├── uploads/
        └── converted/
```

**When MinIO writes to `/data/videos/file.mp4`:**
1. File is written to the PVC (persistent storage)
2. File survives pod restarts, crashes, updates
3. Even if MinIO pod is deleted, file remains on PVC

### **Verify Mounts**

```bash
# Check which pods use which PVCs
kubectl get pods -n video-processing -o custom-columns=POD:metadata.name,PVC:spec.volumes[*].persistentVolumeClaim.claimName

# View mount details for API pod
kubectl describe pod -n video-processing -l app=api | Select-String -Pattern "ClaimName|Mounts:"

# See mounted filesystem inside pod
kubectl exec -n video-processing deployment/api -- df -h /data
```

---

## SQLite Multi-Writer Limitation

### **The Problem**

**SQLite does NOT support multiple concurrent writers across different processes/pods.**

#### **Current Setup:**

| Component | Replicas | Writes to SQLite? | What It Writes |
|-----------|----------|-------------------|----------------|
| **API** | 1 (default) | ✅ YES | Creates new jobs when users upload |
| **Workers** | 1-10 (KEDA) | ✅ YES | Updates job status (pending → completed) |

**Both API and Workers write to the same `jobs.db` file on `database-pvc`!**

### **Why It's a Problem**

**SQLite uses file-level locking:**
- Works fine for single-process, multi-threaded apps
- **Fails** when multiple processes (pods) write simultaneously
- Results in `SQLITE_BUSY` errors and potential corruption

**Example Scenario:**
```
1 API pod + 5 worker pods = 6 processes trying to write
Worker 1: Updates job A → LOCK
Worker 2: Updates job B → SQLITE_BUSY (waits)
Worker 3: Updates job C → SQLITE_BUSY (waits)
API: Creates job D → SQLITE_BUSY (fails!)
```

### **What You'll Experience**

| Load Level | Workers | Result |
|------------|---------|--------|
| **Light** (1-2 workers) | 1-2 | ✅ Works fine |
| **Medium** (3-5 workers) | 3-5 | ⚠️ Occasional "database is locked" warnings |
| **Heavy** (8-10 workers) | 8-10 | ❌ Frequent lock errors, some updates fail |

### **Why RWX Doesn't Help**

**Common Misconception:**
> "I set `accessModes: ReadWriteMany`, so multiple pods can write!"

**Reality:**
- ✅ **RWX allows multiple pods to MOUNT the volume**
- ❌ **RWX does NOT make SQLite support concurrent writes**
- SQLite's limitation is at the **application level**, not storage level

### **Solutions**

#### **For This Demo (Current Setup):**
✅ **Keep API at 1 replica** (already the default)
```yaml
# k8s/api-deployment.yaml
spec:
  replicas: 1  # Don't scale beyond 1
```

⚠️ **Workers can scale** (they mostly write at different times)
- Expect occasional lock errors under heavy load
- Acceptable for demos and testing

#### **For Production:**
🚀 **Replace SQLite with PostgreSQL or MySQL**
- True multi-writer support
- Designed for concurrent connections
- Handles 100+ simultaneous writers

**Migration Path:**
1. Deploy PostgreSQL with a PVC
2. Update `shared/database.py` to use `psycopg2` or `mysql-connector`
3. Update connection strings in ConfigMap
4. Scale API to 2+ replicas safely

---

## Viewing Your Data

### **1. SQLite Database (database-pvc)**

#### **Query from Pod:**
```bash
kubectl exec -n video-processing deployment/api -- python -c "import sqlite3, json; conn = sqlite3.connect('/data/jobs.db'); conn.row_factory = sqlite3.Row; cursor = conn.cursor(); cursor.execute('SELECT * FROM jobs ORDER BY created_at DESC LIMIT 10'); rows = cursor.fetchall(); print(json.dumps([dict(row) for row in rows], indent=2)); conn.close()"
```

#### **Copy to Local Machine:**
```bash
# Copy database file
kubectl cp video-processing/$(kubectl get pod -n video-processing -l app=api -o jsonpath='{.items[0].metadata.name}'):/data/jobs.db ./data/jobs.db

# Open with DB Browser for SQLite or VS Code SQLite extension
```

**Example Job Record:**
```json
{
  "id": "23eabe6b-75e4-4861-9d8d-a270192e85ca",
  "status": "completed",
  "input_path": "uploads/8641adf5-c9fd-4138-80ca-6bb91e9acc8e.mp4",
  "output_path": "converted/23eabe6b-75e4-4861-9d8d-a270192e85ca.mp4",
  "created_at": "2026-01-08T10:39:42.860855",
  "conversion_time_ms": 1270
}
```

---

### **2. MinIO Storage (minio-pvc)**

#### **View Files in Pod:**
```bash
# List video directories
kubectl exec -n video-processing deployment/minio -- ls -lhR /data/videos/

# Check storage usage
kubectl exec -n video-processing deployment/minio -- du -sh /data/videos/*
```

#### **Access via Web Console:**
```bash
# Start port-forward
kubectl port-forward -n video-processing svc/minio 9001:9001

# Open browser: http://localhost:9001
# Login: minioadmin / minioadmin
# Navigate to "videos" bucket to download files
```

**Why MinIO Needs a PVC:**
- MinIO = S3-compatible object storage **software**
- PVC = **Disk** where MinIO stores the actual files
- Without PVC: Files lost on pod restart!

---

### **3. RabbitMQ Queue (rabbitmq-data-rabbitmq-0)**

#### **Check Queue Status:**
```bash
kubectl exec -n video-processing rabbitmq-0 -- rabbitmqctl list_queues name messages
```

#### **View Storage:**
```bash
# Check RabbitMQ data size
kubectl exec -n video-processing rabbitmq-0 -- du -sh /var/lib/rabbitmq/

# List persisted data
kubectl exec -n video-processing rabbitmq-0 -- ls -lh /var/lib/rabbitmq/mnesia/
```

**What's Stored:**
- Queue metadata (durable queues)
- Persisted messages (survive pod restarts)
- Currently: 224KB (mostly configuration)

---

## Common Questions

### **Q: Why do stateful services need PVCs?**

**A:** Without PVCs, all data is stored in the container's filesystem, which is **ephemeral** (temporary).

| Event | Without PVC | With PVC |
|-------|-------------|----------|
| Pod restart | ❌ All data lost | ✅ Data persists |
| Pod crash | ❌ All data lost | ✅ Data persists |
| Deployment update | ❌ All data lost | ✅ Data persists |
| Node failure | ❌ All data lost | ✅ Data persists |

---

### **Q: Can I scale API to 2 pods with SQLite?**

**A:** Technically yes, but you'll get database lock errors:

```bash
# Scale API to 2 replicas
kubectl scale deployment/api -n video-processing --replicas=2

# What happens:
# - Both pods try to write to jobs.db
# - SQLite returns SQLITE_BUSY errors
# - Some job creations fail
# - Not recommended!
```

**Solution:** Keep API at 1 replica OR switch to PostgreSQL.

---

### **Q: How do I know if PVC is initialized?**

**A:** Check the STATUS column:

```bash
kubectl get pvc -n video-processing

# STATUS should be "Bound" (not "Pending")
# If Pending: Storage provisioner issue
# If Bound: PVC is ready and attached to a volume
```

---

### **Q: What's the difference between PVC and the actual storage?**

**A:**

```
PVC (PersistentVolumeClaim)
  ↓ "I need 10Gi of storage"
  ↓
PV (PersistentVolume)
  ↓ Kubernetes provisions actual storage
  ↓
Physical Storage
  ↓ Minikube: Local disk in Docker container
  ↓ Cloud: AWS EBS, Azure Disk, GCP PD
```

---

### **Q: Why is database-pvc only 1Gi but minio-pvc is 10Gi?**

**A:**

- **database-pvc (1Gi):** SQLite database file
  - Current size: 16KB
  - Even with 10,000 jobs: ~10MB
  - 1Gi is more than enough

- **minio-pvc (10Gi):** Video files
  - Videos are large (10MB-1GB each)
  - Need space for uploads + converted versions
  - 10Gi allows ~100-1000 videos (depending on size)

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                       │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  database-pvc (1Gi, RWX)                             │  │
│  │  /data/jobs.db (SQLite)                              │  │
│  └────────┬──────────────────┬──────────────────────────┘  │
│           │                  │                             │
│    ┌──────▼─────┐     ┌─────▼──────┐                      │
│    │  API Pod   │     │ Worker Pods│                      │
│    │ (1 replica)│     │  (1-10)    │                      │
│    └────────────┘     └────────────┘                      │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  minio-pvc (10Gi, RWO)                               │  │
│  │  /data/videos/ (Video files)                         │  │
│  └────────┬─────────────────────────────────────────────┘  │
│           │                                                 │
│    ┌──────▼─────┐                                          │
│    │ MinIO Pod  │                                          │
│    │(1 replica) │                                          │
│    └────────────┘                                          │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  rabbitmq-data-rabbitmq-0 (1Gi, RWO)                 │  │
│  │  /var/lib/rabbitmq/ (Queue data)                     │  │
│  └────────┬─────────────────────────────────────────────┘  │
│           │                                                 │
│    ┌──────▼─────┐                                          │
│    │ RabbitMQ   │                                          │
│    │(1 replica) │                                          │
│    └────────────┘                                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Summary

### **Key Takeaways:**

1. ✅ **PVCs provide persistent storage** - data survives pod restarts
2. ✅ **Mounting connects PVCs to container directories** - like plugging in a USB drive
3. ⚠️ **SQLite + multiple writers = problems** - keep API at 1 replica
4. ✅ **RWX allows multiple mounts** - but doesn't fix SQLite's limitation
5. ✅ **Each service has its own PVC** - database, videos, and queue are separate
6. 🚀 **For production: Use PostgreSQL** - designed for concurrent access

### **Quick Reference Commands:**

```bash
# Check all PVCs
kubectl get pvc -n video-processing

# View which pods use which PVCs
kubectl get pods -n video-processing -o custom-columns=POD:metadata.name,PVC:spec.volumes[*].persistentVolumeClaim.claimName

# Copy SQLite database locally
kubectl cp video-processing/$(kubectl get pod -n video-processing -l app=api -o jsonpath='{.items[0].metadata.name}'):/data/jobs.db ./data/jobs.db

# Access MinIO console
kubectl port-forward -n video-processing svc/minio 9001:9001
# Open: http://localhost:9001

# Check RabbitMQ queue
kubectl exec -n video-processing rabbitmq-0 -- rabbitmqctl list_queues
```

---

**Last Updated:** 2026-01-08  
**Related Docs:**
- [MINIKUBE.md](MINIKUBE.md) - Deployment guide
- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues
