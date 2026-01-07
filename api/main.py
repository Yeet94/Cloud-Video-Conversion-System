# FastAPI Video Processing API Service
import sys
import os
import uuid
import json
import logging
from datetime import timedelta
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
import pika
from minio import Minio
from minio.error import S3Error

# Add shared module to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared import (
    get_settings,
    init_database,
    create_job,
    get_job,
    get_all_jobs,
    get_job_counts,
    JobStatus,
    JobCreate,
    JobResponse,
    UploadURLRequest,
    UploadURLResponse,
    DownloadURLResponse,
    QueueMessage,
    HealthResponse
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Prometheus Metrics
REQUEST_COUNT = Counter(
    'api_requests_total',
    'Total API requests',
    ['method', 'endpoint', 'status_code']
)

INGESTION_RATE = Counter(
    'api_ingestion_rate_total',
    'Total video uploads and job queuing operations',
    ['operation']
)

REQUEST_DURATION = Histogram(
    'api_request_duration_seconds',
    'API request duration in seconds',
    ['method', 'endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

ACTIVE_JOBS = Gauge(
    'api_active_jobs',
    'Number of jobs by status',
    ['status']
)

QUEUE_SIZE = Gauge(
    'api_queue_messages_published',
    'Total messages published to queue'
)

RABBITMQ_QUEUE_DEPTH = Gauge(
    'rabbitmq_queue_depth',
    'Current number of messages in RabbitMQ queue',
    ['queue']
)

# Global connections
minio_client: Optional[Minio] = None
rabbitmq_connection: Optional[pika.BlockingConnection] = None
rabbitmq_channel = None


def get_minio_client(endpoint: Optional[str] = None) -> Minio:
    """Get or create MinIO client for internal operations."""
    global minio_client
    
    # If a specific endpoint is requested (e.g. for external URLs), create a new client
    if endpoint:
        return Minio(
            endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure
        )

    if minio_client is None:
        minio_client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure
        )
        logger.info(f"MinIO client initialized: {settings.minio_endpoint}")
    
    return minio_client




def get_rabbitmq_channel():
    """Get or create RabbitMQ channel with automatic reconnection."""
    global rabbitmq_connection, rabbitmq_channel
    
    # Check if connection exists and is still alive
    if rabbitmq_connection is not None and not rabbitmq_connection.is_closed:
        try:
            # Test if channel is still usable by doing a passive queue check
            # This will raise an exception if the connection is stale
            if rabbitmq_channel and rabbitmq_channel.is_open:
                rabbitmq_channel.queue_declare(
                    queue=settings.rabbitmq_queue,
                    passive=True  # Don't create, just check
                )
                # Connection is good!
                return rabbitmq_channel
            else:
                # Channel is closed, need new one
                logger.warning("RabbitMQ channel is closed, creating new channel")
                rabbitmq_channel = None
        except Exception as e:
            # Connection is stale/broken, force reconnect
            logger.warning(f"RabbitMQ connection test failed: {e}, reconnecting...")
            rabbitmq_connection = None
            rabbitmq_channel = None
    
    # Create new connection
    try:
        credentials = pika.PlainCredentials(
            settings.rabbitmq_user,
            settings.rabbitmq_password
        )
        parameters = pika.ConnectionParameters(
            host=settings.rabbitmq_host,
            port=settings.rabbitmq_port,
            virtual_host=settings.rabbitmq_vhost,
            credentials=credentials,
            heartbeat=600,
            blocked_connection_timeout=300
        )
        rabbitmq_connection = pika.BlockingConnection(parameters)
        rabbitmq_channel = rabbitmq_connection.channel()
        
        # Declare queue with durability
        rabbitmq_channel.queue_declare(
            queue=settings.rabbitmq_queue,
            durable=True,
            arguments={
                'x-message-ttl': 86400000  # 24 hours
            }
        )
        logger.info(f"Connected to RabbitMQ, queue: {settings.rabbitmq_queue}")
        return rabbitmq_channel
        
    except Exception as e:
        logger.error(f"Failed to connect to RabbitMQ: {e}")
        rabbitmq_connection = None
        rabbitmq_channel = None
        raise


def update_job_metrics():
    """Update Prometheus metrics for job counts."""
    try:
        counts = get_job_counts()
        for status in JobStatus:
            ACTIVE_JOBS.labels(status=status.value).set(counts.get(status.value, 0))
    except Exception as e:
        logger.error(f"Failed to update job metrics: {e}")


def update_rabbitmq_metrics():
    """Update Prometheus metrics for RabbitMQ queue depth."""
    try:
        channel = get_rabbitmq_channel()
        # Use passive=True to check queue without creating it
        method_frame = channel.queue_declare(queue=settings.rabbitmq_queue, passive=True)
        queue_depth = method_frame.method.message_count
        RABBITMQ_QUEUE_DEPTH.labels(queue=settings.rabbitmq_queue).set(queue_depth)
        logger.debug(f"RabbitMQ queue depth: {queue_depth}")
    except Exception as e:
        logger.error(f"Failed to update RabbitMQ metrics: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting API service...")
    init_database(settings.database_path)
    logger.info("Database initialized")
    
    # Pre-initialize connections
    try:
        get_minio_client()
        logger.info("MinIO client initialized")
    except Exception as e:
        logger.warning(f"MinIO not yet available: {e}")
    
    try:
        get_rabbitmq_channel()
        logger.info("RabbitMQ connection established")
    except Exception as e:
        logger.warning(f"RabbitMQ not yet available: {e}")
    
    update_job_metrics()
    
    yield
    
    # Shutdown
    global rabbitmq_connection
    if rabbitmq_connection and not rabbitmq_connection.is_closed:
        rabbitmq_connection.close()
    logger.info("API service shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Video Conversion API",
    description="Distributed video processing service with FFmpeg",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    update_job_metrics()
    update_rabbitmq_metrics()  # Add RabbitMQ metrics
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check health of all service dependencies."""
    rabbitmq_ok = False
    minio_ok = False
    database_ok = False
    
    # Check RabbitMQ
    try:
        channel = get_rabbitmq_channel()
        rabbitmq_ok = channel is not None and not rabbitmq_connection.is_closed
    except Exception as e:
        logger.warning(f"RabbitMQ health check failed: {e}")
    
    # Check MinIO
    try:
        client = get_minio_client()
        minio_ok = client.bucket_exists(settings.minio_bucket)
    except Exception as e:
        logger.warning(f"MinIO health check failed: {e}")
    
    # Check Database
    try:
        get_job_counts()
        database_ok = True
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
    
    status = "healthy" if all([rabbitmq_ok, minio_ok, database_ok]) else "degraded"
    
    REQUEST_COUNT.labels(method='GET', endpoint='/health', status_code=200).inc()
    
    return HealthResponse(
        status=status,
        version="1.0.0",
        rabbitmq=rabbitmq_ok,
        minio=minio_ok,
        database=database_ok
    )


@app.post("/upload/request", response_model=UploadURLResponse)
async def request_upload_url(request: UploadURLRequest):
    """Generate a presigned URL for uploading a video file."""
    import time
    start_time = time.time()
    
    try:
        client = get_minio_client()
        
        # Generate unique path for upload
        job_id = str(uuid.uuid4())
        file_ext = os.path.splitext(request.filename)[1] or '.mp4'
        object_path = f"uploads/{job_id}{file_ext}"
        
        # Generate presigned URL using internal client
        upload_url = client.presigned_put_object(
            settings.minio_bucket,
            object_path,
            expires=timedelta(hours=1)
        )
        
        # Rewrite URL to use external endpoint for browser access
        upload_url = upload_url.replace(
            f"http://{settings.minio_endpoint}",
            f"http://{settings.minio_external_endpoint}"
        )
        
        INGESTION_RATE.labels(operation='upload_url_generated').inc()
        REQUEST_COUNT.labels(method='POST', endpoint='/upload/request', status_code=200).inc()
        REQUEST_DURATION.labels(method='POST', endpoint='/upload/request').observe(time.time() - start_time)
        
        return UploadURLResponse(
            upload_url=upload_url,
            object_path=object_path,
            job_id=job_id,
            expires_in=3600
        )
    
    except S3Error as e:
        logger.error(f"MinIO error generating upload URL: {e}")
        REQUEST_COUNT.labels(method='POST', endpoint='/upload/request', status_code=500).inc()
        raise HTTPException(status_code=500, detail=f"Storage error: {str(e)}")


@app.post("/jobs", response_model=JobResponse)
async def create_conversion_job(job_request: JobCreate):
    """Create a new video conversion job and enqueue it for processing."""
    import time
    start_time = time.time()
    
    try:
        job_id = str(uuid.uuid4())
        
        # Create job in database
        job = create_job(
            job_id=job_id,
            input_path=job_request.input_path,
            output_format=job_request.output_format or "mp4",
            db_path=settings.database_path
        )
        
        # Create queue message
        message = QueueMessage.create(
            job_id=job_id,
            input_path=job_request.input_path,
            output_format=job_request.output_format or "mp4"
        )
        
        # Publish to RabbitMQ
        channel = get_rabbitmq_channel()
        channel.basic_publish(
            exchange='',
            routing_key=settings.rabbitmq_queue,
            body=message.model_dump_json(),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Persistent message
                content_type='application/json'
            )
        )
        
        INGESTION_RATE.labels(operation='job_created').inc()
        INGESTION_RATE.labels(operation='message_published').inc()
        QUEUE_SIZE.inc()
        REQUEST_COUNT.labels(method='POST', endpoint='/jobs', status_code=201).inc()
        REQUEST_DURATION.labels(method='POST', endpoint='/jobs').observe(time.time() - start_time)
        
        logger.info(f"Created job {job_id} and enqueued for processing")
        
        return job
    
    except Exception as e:
        logger.error(f"Failed to create job: {e}")
        REQUEST_COUNT.labels(method='POST', endpoint='/jobs', status_code=500).inc()
        raise HTTPException(status_code=500, detail=f"Failed to create job: {str(e)}")


@app.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str):
    """Get the status and details of a specific job."""
    import time
    start_time = time.time()
    
    job = get_job(job_id, settings.database_path)
    
    if job is None:
        REQUEST_COUNT.labels(method='GET', endpoint='/jobs/{job_id}', status_code=404).inc()
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    REQUEST_COUNT.labels(method='GET', endpoint='/jobs/{job_id}', status_code=200).inc()
    REQUEST_DURATION.labels(method='GET', endpoint='/jobs/{job_id}').observe(time.time() - start_time)
    
    return job


@app.get("/jobs", response_model=List[JobResponse])
async def list_jobs(
    status: Optional[JobStatus] = Query(None, description="Filter by job status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of jobs to return")
):
    """List all jobs with optional status filter."""
    import time
    start_time = time.time()
    
    jobs = get_all_jobs(status=status, limit=limit, db_path=settings.database_path)
    
    REQUEST_COUNT.labels(method='GET', endpoint='/jobs', status_code=200).inc()
    REQUEST_DURATION.labels(method='GET', endpoint='/jobs').observe(time.time() - start_time)
    
    return jobs


@app.get("/download/{job_id}", response_model=DownloadURLResponse)
async def get_download_url(job_id: str):
    """Get a presigned URL for downloading a completed video."""
    import time
    start_time = time.time()
    
    job = get_job(job_id, settings.database_path)
    
    if job is None:
        REQUEST_COUNT.labels(method='GET', endpoint='/download/{job_id}', status_code=404).inc()
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    if job.status != JobStatus.COMPLETED:
        REQUEST_COUNT.labels(method='GET', endpoint='/download/{job_id}', status_code=400).inc()
        raise HTTPException(
            status_code=400,
            detail=f"Job is not completed. Current status: {job.status.value}"
        )
    
    if not job.output_path:
        REQUEST_COUNT.labels(method='GET', endpoint='/download/{job_id}', status_code=500).inc()
        raise HTTPException(status_code=500, detail="Output path not available")
    
    try:
        # Generate presigned URL using internal client
        client = get_minio_client()
        download_url = client.presigned_get_object(
            settings.minio_bucket,
            job.output_path,
            expires=timedelta(hours=1)
        )
        
        # Rewrite URL to use external endpoint for browser access
        download_url = download_url.replace(
            f"http://{settings.minio_endpoint}",
            f"http://{settings.minio_external_endpoint}"
        )
        
        REQUEST_COUNT.labels(method='GET', endpoint='/download/{job_id}', status_code=200).inc()
        REQUEST_DURATION.labels(method='GET', endpoint='/download/{job_id}').observe(time.time() - start_time)
        
        return DownloadURLResponse(
            download_url=download_url,
            expires_in=3600
        )
    
    except S3Error as e:
        logger.error(f"MinIO error generating download URL: {e}")
        REQUEST_COUNT.labels(method='GET', endpoint='/download/{job_id}', status_code=500).inc()
        raise HTTPException(status_code=500, detail=f"Storage error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True
    )
