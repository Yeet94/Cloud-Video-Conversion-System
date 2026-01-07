# Video Processing Worker Service
import sys
import os
import json
import time
import signal
import logging
import subprocess
import tempfile
import threading
import psutil
from typing import Optional
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

import pika
from minio import Minio
from minio.error import S3Error
from prometheus_client import Counter, Histogram, Gauge, start_http_server

# Add shared module to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared import (
    get_settings,
    init_database,
    get_job,
    update_job_status,
    JobStatus,
    QueueMessage
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Prometheus Metrics
JOBS_PROCESSED = Counter(
    'worker_jobs_processed_total',
    'Total jobs processed by workers',
    ['status']
)

CONVERSION_TIME = Histogram(
    'worker_conversion_time_seconds',
    'Time taken for video conversion',
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600]
)

FAILURE_RATE = Counter(
    'worker_failure_rate_total',
    'Total failures by type',
    ['failure_type']
)

ACTIVE_JOBS = Gauge(
    'worker_active_jobs',
    'Currently processing jobs'
)

DOWNLOAD_TIME = Histogram(
    'worker_download_time_seconds',
    'Time to download video from MinIO',
    buckets=[0.5, 1, 2, 5, 10, 30, 60]
)

UPLOAD_TIME = Histogram(
    'worker_upload_time_seconds',
    'Time to upload video to MinIO',
    buckets=[0.5, 1, 2, 5, 10, 30, 60]
)

# Global state
shutdown_event = threading.Event()
current_ffmpeg_process: Optional[subprocess.Popen] = None


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP handler for health and readiness checks."""
    
    def do_GET(self):
        """Handle GET requests for health/readiness."""
        if self.path == '/health':
            # Liveness probe - always return 200 if worker is running
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'alive'}).encode())
            
        elif self.path == '/ready':
            # Readiness probe - check CPU and memory usage
            try:
                cpu_percent = psutil.cpu_percent(interval=0.1)
                memory_percent = psutil.virtual_memory().percent
                
                # Worker is ready if:
                # - CPU usage < 85%
                # - Memory usage < 90%
                # - Not shutting down
                is_ready = (
                    cpu_percent < 85 and 
                    memory_percent < 90 and 
                    not shutdown_event.is_set()
                )
                
                status_code = 200 if is_ready else 503
                self.send_response(status_code)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                
                response = {
                    'ready': is_ready,
                    'cpu_percent': round(cpu_percent, 2),
                    'memory_percent': round(memory_percent, 2),
                    'active_jobs': ACTIVE_JOBS._value._value  # Access gauge value
                }
                self.wfile.write(json.dumps(response).encode())
                
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


def start_health_server(port=8080):
    """Start health check server in background thread."""
    try:
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"Health check server started on port {port}")
        # Give the server a moment to start
        time.sleep(0.5)
        return server
    except Exception as e:
        logger.error(f"Failed to start health check server on port {port}: {e}")
        # Return None but don't crash - worker can still function
        return None


def get_minio_client() -> Minio:
    """Create MinIO client."""
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure
    )


def download_video(client: Minio, object_path: str, local_path: str) -> bool:
    """Download video from MinIO to local path."""
    start_time = time.time()
    try:
        client.fget_object(settings.minio_bucket, object_path, local_path)
        download_time = time.time() - start_time
        DOWNLOAD_TIME.observe(download_time)
        logger.info(f"Downloaded {object_path} in {download_time:.2f}s")
        return True
    except S3Error as e:
        logger.error(f"Failed to download {object_path}: {e}")
        FAILURE_RATE.labels(failure_type='download_failed').inc()
        return False


def upload_video(client: Minio, local_path: str, object_path: str) -> bool:
    """Upload converted video to MinIO."""
    start_time = time.time()
    try:
        # Determine content type
        content_type = 'video/mp4'
        if object_path.endswith('.webm'):
            content_type = 'video/webm'
        elif object_path.endswith('.mkv'):
            content_type = 'video/x-matroska'
        elif object_path.endswith('.avi'):
            content_type = 'video/x-msvideo'
        elif object_path.endswith('.mov'):
            content_type = 'video/quicktime'
        elif object_path.endswith('.gif'):
            content_type = 'image/gif'
        elif object_path.endswith('.mp3'):
            content_type = 'audio/mpeg'
        
        client.fput_object(
            settings.minio_bucket,
            object_path,
            local_path,
            content_type=content_type
        )
        upload_time = time.time() - start_time
        UPLOAD_TIME.observe(upload_time)
        logger.info(f"Uploaded {object_path} in {upload_time:.2f}s")
        return True
    except S3Error as e:
        logger.error(f"Failed to upload {object_path}: {e}")
        FAILURE_RATE.labels(failure_type='upload_failed').inc()
        return False


def convert_video(input_path: str, output_path: str, output_format: str) -> tuple:
    """
    Convert video using FFmpeg.
    Returns (success: bool, duration_ms: int, error_message: str)
    """
    global current_ffmpeg_process
    
    start_time = time.time()
    
    # Build FFmpeg command
    cmd = [
        'ffmpeg',
        '-i', input_path,
        '-y',  # Overwrite output
        '-hide_banner',
        '-loglevel', 'warning',
    ]
    
    # Add codec settings based on output format
    if output_format == 'mp4':
        cmd.extend([
            '-c:v', settings.ffmpeg_video_codec,
            '-preset', settings.ffmpeg_preset,
            '-crf', str(settings.ffmpeg_crf),
            '-c:a', settings.ffmpeg_audio_codec,
            '-b:a', '128k',
            '-movflags', '+faststart'
        ])
    elif output_format == 'webm':
        cmd.extend([
            '-c:v', 'libvpx-vp9',
            '-crf', '30',
            '-b:v', '0',
            '-c:a', 'libopus',
            '-b:a', '128k'
        ])
    elif output_format == 'gif':
        cmd.extend([
            '-vf', 'fps=15,scale=480:-1:flags=lanczos',
            '-c:v', 'gif'
        ])
    elif output_format == 'avi':
        cmd.extend([
            '-c:v', 'mpeg4',
            '-q:v', '5',
            '-c:a', 'libmp3lame',
            '-q:a', '2'
        ])
    elif output_format == 'mov':
        cmd.extend([
            '-c:v', settings.ffmpeg_video_codec,
            '-c:a', settings.ffmpeg_audio_codec,
            '-f', 'mov'
        ])
    elif output_format == 'mkv':
        cmd.extend([
            '-c:v', settings.ffmpeg_video_codec,
            '-c:a', settings.ffmpeg_audio_codec,
            '-f', 'matroska'
        ])
    elif output_format == 'mp3':
        cmd.extend([
            '-vn',  # No video
            '-c:a', 'libmp3lame',
            '-b:a', '192k'
        ])
    else:
        # Default to copy
        cmd.extend(['-c', 'copy'])
    
    cmd.append(output_path)
    
    logger.info(f"Running FFmpeg: {' '.join(cmd)}")
    
    try:
        current_ffmpeg_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        stdout, stderr = current_ffmpeg_process.communicate()
        return_code = current_ffmpeg_process.returncode
        current_ffmpeg_process = None
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        if return_code != 0:
            error_msg = stderr.decode('utf-8', errors='replace')
            logger.error(f"FFmpeg failed with code {return_code}: {error_msg}")
            FAILURE_RATE.labels(failure_type='ffmpeg_error').inc()
            return False, duration_ms, error_msg
        
        CONVERSION_TIME.observe(duration_ms / 1000)
        logger.info(f"Conversion completed in {duration_ms}ms")
        return True, duration_ms, None
        
    except Exception as e:
        current_ffmpeg_process = None
        duration_ms = int((time.time() - start_time) * 1000)
        error_msg = str(e)
        logger.error(f"FFmpeg exception: {error_msg}")
        FAILURE_RATE.labels(failure_type='ffmpeg_exception').inc()
        return False, duration_ms, error_msg


def process_job(message: QueueMessage) -> bool:
    """Process a single video conversion job."""
    job_id = message.job_id
    logger.info(f"Processing job {job_id}")
    
    ACTIVE_JOBS.inc()
    
    try:
        # Update job status to processing
        update_job_status(
            job_id=job_id,
            status=JobStatus.PROCESSING,
            db_path=settings.database_path
        )
        
        # Create MinIO client
        minio_client = get_minio_client()
        
        # Create temp directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            # Determine file extensions
            input_ext = os.path.splitext(message.input_path)[1] or '.mp4'
            output_ext = f'.{message.output_format}'
            
            input_local = os.path.join(temp_dir, f'input{input_ext}')
            output_local = os.path.join(temp_dir, f'output{output_ext}')
            
            # Download input video
            logger.info(f"Downloading {message.input_path}")
            if not download_video(minio_client, message.input_path, input_local):
                update_job_status(
                    job_id=job_id,
                    status=JobStatus.FAILED,
                    error_message="Failed to download input file",
                    db_path=settings.database_path
                )
                JOBS_PROCESSED.labels(status='failed').inc()
                return False
            
            # Convert video
            logger.info(f"Converting video to {message.output_format}")
            success, duration_ms, error_msg = convert_video(
                input_local,
                output_local,
                message.output_format
            )
            
            if not success:
                update_job_status(
                    job_id=job_id,
                    status=JobStatus.FAILED,
                    error_message=error_msg or "FFmpeg conversion failed",
                    conversion_time_ms=duration_ms,
                    db_path=settings.database_path
                )
                JOBS_PROCESSED.labels(status='failed').inc()
                return False
            
            # Upload converted video
            output_path = f"converted/{job_id}{output_ext}"
            logger.info(f"Uploading to {output_path}")
            
            if not upload_video(minio_client, output_local, output_path):
                update_job_status(
                    job_id=job_id,
                    status=JobStatus.FAILED,
                    error_message="Failed to upload converted file",
                    conversion_time_ms=duration_ms,
                    db_path=settings.database_path
                )
                JOBS_PROCESSED.labels(status='failed').inc()
                return False
            
            # Update job as completed
            update_job_status(
                job_id=job_id,
                status=JobStatus.COMPLETED,
                output_path=output_path,
                conversion_time_ms=duration_ms,
                db_path=settings.database_path
            )
            
            logger.info(f"Job {job_id} completed successfully in {duration_ms}ms")
            JOBS_PROCESSED.labels(status='success').inc()
            return True
            
    except Exception as e:
        logger.exception(f"Unexpected error processing job {job_id}: {e}")
        update_job_status(
            job_id=job_id,
            status=JobStatus.FAILED,
            error_message=str(e),
            db_path=settings.database_path
        )
        JOBS_PROCESSED.labels(status='failed').inc()
        FAILURE_RATE.labels(failure_type='unexpected_error').inc()
        return False
    finally:
        ACTIVE_JOBS.dec()


def on_message(channel, method, properties, body):
    """RabbitMQ message callback."""
    try:
        # Parse message
        data = json.loads(body)
        message = QueueMessage(**data)
        
        logger.info(f"Received job {message.job_id}")
        
        # Check for shutdown
        if shutdown_event.is_set():
            logger.info("Shutdown requested, rejecting message for requeue")
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            return
        
        # Process the job
        success = process_job(message)
        
        if success:
            # Acknowledge successful processing
            channel.basic_ack(delivery_tag=method.delivery_tag)
        else:
            # NACK with requeue for retry (up to a point)
            # In a real system, you'd track retry count
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            FAILURE_RATE.labels(failure_type='nack').inc()
            
    except json.JSONDecodeError as e:
        logger.error(f"Invalid message format: {e}")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        FAILURE_RATE.labels(failure_type='invalid_message').inc()
    except Exception as e:
        logger.exception(f"Error processing message: {e}")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        FAILURE_RATE.labels(failure_type='processing_error').inc()


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global current_ffmpeg_process
    
    logger.info(f"Received signal {signum}, initiating graceful shutdown")
    shutdown_event.set()
    
    # Kill any running FFmpeg process
    if current_ffmpeg_process:
        logger.info("Terminating active FFmpeg process")
        current_ffmpeg_process.terminate()
        try:
            current_ffmpeg_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            current_ffmpeg_process.kill()


def main():
    """Main worker entry point."""
    logger.info("Starting video processing worker...")
    
    # Initialize database
    init_database(settings.database_path)
    logger.info("Database initialized")
    
    # Start Prometheus metrics server
    start_http_server(settings.metrics_port)
    logger.info(f"Prometheus metrics server started on port {settings.metrics_port}")
    
    # Start health check server for readiness/liveness probes
    logger.info("Starting health check server on port 8080...")
    health_server = start_health_server(port=8080)
    if health_server:
        logger.info("✓ Health check server started successfully")
    else:
        logger.warning("⚠ Health check server failed to start - probes will fail!")
    
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Connect to RabbitMQ with retry
    max_retries = 30
    retry_delay = 5
    
    for attempt in range(max_retries):
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
            
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            
            # Declare queue (idempotent)
            channel.queue_declare(
                queue=settings.rabbitmq_queue,
                durable=True,
                arguments={'x-message-ttl': 86400000}
            )
            
            # Set prefetch to 1 for fair dispatch [Important to tell RabbitMQ not to give more than one message to a worker]
            channel.basic_qos(prefetch_count=1)
            
            logger.info(f"Connected to RabbitMQ, consuming from queue: {settings.rabbitmq_queue}")
            break
            
        except pika.exceptions.AMQPConnectionError as e:
            logger.warning(f"RabbitMQ connection attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                logger.error("Failed to connect to RabbitMQ after max retries")
                sys.exit(1)
    
    # Set up consumer
    channel.basic_consume(
        queue=settings.rabbitmq_queue,
        on_message_callback=on_message,
        auto_ack=False
    )
    
    logger.info("Worker ready, waiting for jobs...")
    
    try:
        while not shutdown_event.is_set():
            connection.process_data_events(time_limit=1)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    finally:
        logger.info("Closing RabbitMQ connection")
        try:
            channel.stop_consuming()
            connection.close()
        except Exception as e:
            logger.warning(f"Error closing connection: {e}")
    
    logger.info("Worker shutdown complete")


if __name__ == "__main__":
    main()
