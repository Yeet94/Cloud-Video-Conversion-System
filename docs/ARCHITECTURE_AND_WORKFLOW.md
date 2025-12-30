# Cloud Video Conversion System: Architecture & Workflow Guide

This document provides an in-depth look at the architecture, component interactions, and data flows within the Cloud Video Conversion System. It is designed to help developers and operators understand the inner workings of the application.

## 1. System Overview

The Cloud Video Conversion System is a distributed, event-driven application designed to process video transcoding jobs at scale. It leverages a microservices architecture to decouple ingestion, processing, and storage, enabling independent scaling and fault tolerance.

### Core Philosophy
*   **Event-Driven**: Components communicate asynchronously via RabbitMQ. The API does not wait for video conversion to finish; it offloads the work.
*   **Stateless Processing**: Worker nodes are stateless. They fetch data, process it, and upload results, making them easy to replace or scale.
*   **Cloud-Native**: Designed for Kubernetes with observability (Prometheus/Grafana) and autoscaling (KEDA) built-in.

---

## 2. Detailed Architecture

### 2.1 Component Breakdown

#### **1. Frontend (UI)**
*   **Tech Stack**: Static HTML/JS served by Nginx.
*   **Role**: Provides a user-friendly interface for users to upload videos and track status.
*   **Interaction**: Direct browser-to-API communication.
*   **Key Features**:
    *   Direct-to-MinIO uploads using presigned URLs (bypassing the API server for heavy data transfer).
    *   Real-time job status polling.

#### **2. API Service (Gateway)**
*   **Tech Stack**: Python (FastAPI).
*   **Role**: The entry point for all control operations.
*   **Responsibilities**:
    *   **Authentication/Validation**: Validates requests.
    *   **Presigned URL Generation**: secure URLs for uploading/downloading from MinIO.
    *   **Job Management**: Creates job records in SQLite and publishes tasks to RabbitMQ.
    *   **Metrics**: Exposes Prometheus metrics (`api_requests_total`, `api_ingestion_rate_total`).

#### **3. Message Broker (RabbitMQ)**
*   **Role**: Decouples the API from the Workers. Acts as a buffer for high traffic.
*   **Queue**: `video-jobs`.
*   **Durability**: Messages are persistent to survive broker restarts.

#### **4. Worker Service (Processing)**
*   **Tech Stack**: Python (Custom Consumer) + FFmpeg.
*   **Role**: Consumes messages and performs the CPU-intensive video conversion.
*   **Workflow**:
    1.  `ACK`: Acknowledges message receipt (or later after processing depending on config).
    2.  `Download`: Fetches raw video from MinIO.
    3.  `Transcode`: Runs FFmpeg subprocess.
    4.  `Upload`: Pushes converted video back to MinIO.
    5.  `Update`: Updates status in SQLite.
*   **Fault Tolerance**: If a worker crashes, the unacknowledged message is returned to the queue (NACK) for another worker to pick up.

#### **5. Object Storage (MinIO)**
*   **Role**: Stores raw and processed video files.
*   **Bucket Structure**:
    *   `videos/uploads/{uuid}.{ext}`: Raw uploaded files.
    *   `videos/processed/{uuid}.{ext}`: Converted files.

#### **6. Database (SQLite)**
*   **Role**: Persistent store for job metadata (ID, status, timestamps).
*   **Path**: `/data/jobs.db` (Mounted volume).
*   **Note**: In a production cloud environment, this would be replaced by a managed SQL service (PostgreSQL/MySQL) to share state across multiple API replicas.
*   **Command to check the database**: `docker exec api python /data/check_db.py`


#### **7. Autoscaler (KEDA)**
*   **Role**: Automatically scales the number of Worker pods based on the RabbitMQ queue length.
*   **Trigger**: If queue length > 10, add more pods (configurable).

---

## 3. Data Flow: Life of a Video Job

The timeline of a single conversion request follows these steps:

### Phase 1: Ingestion
1.  **User Request**: User clicks "Upload" on Frontend.
2.  **Get URL**: Frontend calls `POST /upload/request` on API.
3.  **Presign**: API generates a secure MinIO PUT URL and returns it.
4.  **Direct Upload**: Browser uploads the large video file directly to MinIO.
5.  **Job Creation**: Frontend calls `POST /jobs` with the file location.
6.  **Enqueue**: API saves job as `QUEUED` in DB and publishes message to RabbitMQ.

### Phase 2: Processing
7.  **Consume**: An available Worker pulls the message.
8.  **Update Status**: Worker updates DB state to `PROCESSING`.
9.  **Download**: Worker downloads the source file from MinIO to local temp storage.
10. **Convert**: Worker spawns `ffmpeg` process to convert format (e.g., AVI -> MP4).
11. **Upload**: Worker uploads the result to MinIO (`processed/`).

### Phase 3: Completion
12. **Finalize**: Worker updates DB state to `COMPLETED` (or `FAILED` on error).
13. **Notify/Poll**: Frontend polls `GET /jobs/{id}` and sees `COMPLETED` status.
14. **Download**: User clicks "Download" -> Frontend requests presigned GET URL -> User downloads file.

---

## 4. Message Structure

Messages in RabbitMQ are JSON payloads containing essential job info:

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "input_path": "uploads/source_video.avi",
  "output_format": "mp4",
  "output_path": "processed/final_video.mp4"
}
```

---

## 5. Monitoring & Observability

### Key Metrics
*   **Throughput**: How many videos are converted per minute.
*   **Latency**: Time taken from `QUEUED` to `COMPLETED`.
*   **Error Rate**: Percentage of failed FFmpeg jobs.
*   **Queue Depth**: Lag in RabbitMQ (primary scaling metric).

### Dashboard Panels
1.  **System Health**: Up/Down status of all pods.
2.  **Business Logic**: Total jobs completed vs. failed.
3.  **Resources**: CPU/Memory usage of active Workers (spikes during FFmpeg).

---

## 6. Fault Tolerance Strategies

The system is designed to self-heal:

| Failure Scenario | System Response |
|------------------|-----------------|
| **Worker Crash** | Message is not ACKed. RabbitMQ requeues it after timeout. Another worker picks it up. |
| **RabbitMQ Down** | API buffers/fails gracefully. Workers retry connection until broker returns. |
| **API Down** | Frontend shows error. Existing queued jobs continue processing by Workers. |
| **FFmpeg Error** | Worker catches exception, logs error, and marks job `FAILED`. Poison messages are discarded (or moved to DLQ). |

---

## 7. Configuration Reference

Key environment variables to tune the system:

**Worker Settings**
*   `MAX_RETRIES`: Number of times to retry a failed conversion (Default: 3).
*   `FFMPEG_THREADS`: limit CPU usage per worker (Default: auto).

**API Settings**
*   `MAX_UPLOAD_SIZE`: Limit file size for presigned URLs (Default: 1GB).
*   `JOB_TIMEOUT`: Time before a processing job is considered "stuck" (implemented via visibility timeout).
