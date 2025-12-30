"""
Locust Load Testing for Video Processing System

This file defines load test scenarios for the video conversion API.
Run with: locust -f locustfile.py --host=http://localhost:8000
"""

import os
import time
import random
import string
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner


def random_filename():
    """Generate a random video filename."""
    chars = string.ascii_lowercase + string.digits
    name = ''.join(random.choice(chars) for _ in range(10))
    extensions = ['mp4', 'avi', 'mkv', 'mov', 'webm']
    ext = random.choice(extensions)
    return f"test_video_{name}.{ext}"


class VideoProcessingUser(HttpUser):
    """
    Simulates a user interacting with the video processing API.
    
    User behavior:
    1. Request upload URL
    2. Create conversion job
    3. Poll for job status
    4. Download completed video
    """
    
    wait_time = between(3, 5)  # Wait 3-5 seconds between tasks
    
    def on_start(self):
        """Called when a user starts."""
        self.pending_jobs = []
        self.completed_jobs = []
    
    @task(10)
    def create_job_flow(self):
        """
        Full flow: request upload URL -> create job.
        This is the most common operation (weight 10).
        """
        # Step 1: Request upload URL
        filename = random_filename()
        with self.client.post(
            "/upload/request",
            json={"filename": filename, "content_type": "video/mp4"},
            name="/upload/request",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                job_id = data.get("job_id")
                object_path = data.get("object_path")
                upload_url = data.get("upload_url")
                
                # FIX: If running in Docker (Locust), we can't reach 'localhost:9000'.
                # We must replace it with 'minio:9000'.
                if "localhost:9000" in upload_url and os.environ.get("LOCUST_HOST") != "http://localhost:8000":
                     upload_url = upload_url.replace("localhost:9000", "minio:9000")
                
                # Step 2: Upload file to MinIO
                # We need to catch this to avoid failing the test if MinIO is slow
                try:
                    with open("/mnt/locust/sample.mp4", "rb") as f:
                        self.client.put(
                            upload_url,
                            data=f,
                            headers={"Content-Type": "video/mp4"},
                            name="MinIO Upload",
                            catch_response=True
                        )
                except FileNotFoundError:
                    # Fallback for local testing without the file
                    self.client.put(
                        upload_url,
                        data="dummy content",
                        headers={"Content-Type": "video/mp4"},
                        name="MinIO Upload (Dummy)"
                    )

                # Step 3: Create conversion job
                # (In real scenario, user would upload file first via presigned URL)
                # Here we simulate that upload happened and create the job
                with self.client.post(
                    "/jobs",
                    json={"input_path": object_path, "output_format": "mp4"},
                    name="/jobs [create]",
                    catch_response=True
                ) as job_response:
                    if job_response.status_code == 200:
                        job_data = job_response.json()
                        self.pending_jobs.append(job_data.get("id"))
                        job_response.success()
                    else:
                        job_response.failure(f"Failed to create job: {job_response.text}")
                
                response.success()
            else:
                response.failure(f"Failed to get upload URL: {response.text}")
    
    @task(5)
    def check_job_status(self):
        """
        Check status of a pending job (weight 5).
        This simulates polling behavior.
        """
        if not self.pending_jobs:
            return
        
        job_id = random.choice(self.pending_jobs)
        
        with self.client.get(
            f"/jobs/{job_id}",
            name="/jobs/{job_id} [status]",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                
                if status == "completed":
                    self.pending_jobs.remove(job_id)
                    self.completed_jobs.append(job_id)
                elif status == "failed":
                    self.pending_jobs.remove(job_id)
                
                response.success()
            elif response.status_code == 404:
                # Job may have been cleaned up
                if job_id in self.pending_jobs:
                    self.pending_jobs.remove(job_id)
                response.success()
            else:
                response.failure(f"Failed to get job status: {response.text}")
    
    @task(3)
    def list_jobs(self):
        """
        List all jobs (weight 3).
        """
        with self.client.get(
            "/jobs?limit=50",
            name="/jobs [list]",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed to list jobs: {response.text}")
    
    @task(2)
    def download_completed_video(self):
        """
        Download a completed video (weight 2).
        """
        if not self.completed_jobs:
            return
        
        job_id = random.choice(self.completed_jobs)
        
        with self.client.get(
            f"/download/{job_id}",
            name="/download/{job_id}",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 400:
                # Job not completed yet
                response.success()
            elif response.status_code == 404:
                # Job cleaned up
                if job_id in self.completed_jobs:
                    self.completed_jobs.remove(job_id)
                response.success()
            else:
                response.failure(f"Failed to get download URL: {response.text}")
    
    @task(1)
    def health_check(self):
        """
        Health check endpoint (weight 1).
        """
        with self.client.get(
            "/health",
            name="/health",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.text}")


class BurstUser(HttpUser):
    """
    Simulates burst traffic - rapid job creation.
    Used to test autoscaling behavior.
    """
    
    wait_time = between(0.1, 0.5)  # Very fast
    
    @task
    def burst_create_jobs(self):
        """Rapidly create jobs to simulate burst traffic."""
        filename = random_filename()
        
        # Request upload URL
        response = self.client.post(
            "/upload/request",
            json={"filename": filename, "content_type": "video/mp4"},
            name="/upload/request [burst]"
        )
        
        if response.status_code == 200:
            data = response.json()
            object_path = data.get("object_path")
            
            # Create job
            self.client.post(
                "/jobs",
                json={"input_path": object_path, "output_format": "mp4"},
                name="/jobs [burst create]"
            )


# Event hooks for custom metrics
@events.request.add_listener
def on_request(request_type, name, response_time, response_length, response, context, exception, **kwargs):
    """Log custom metrics per request."""
    if exception:
        print(f"Request failed: {name} - {exception}")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when load test starts."""
    print("=" * 50)
    print("Video Processing Load Test Started")
    print("=" * 50)
    if isinstance(environment.runner, MasterRunner):
        print(f"Running in distributed mode with {environment.runner.worker_count} workers")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops."""
    print("=" * 50)
    print("Video Processing Load Test Completed")
    print("=" * 50)
