"""
Locust Load Testing for Video Processing System (External Mode)

This file is optimized for running Locust OUTSIDE Kubernetes (on your local machine).
It uses the new /load-test/generate endpoint to create synthetic videos server-side,
avoiding the presigned URL upload complexity.

Run with: locust -f locustfile.py --host=http://localhost/api
Web UI: http://localhost:8089
"""

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
    1. Generate test video (server-side)
    2. Create conversion job
    3. Poll for job status
    4. Download completed video
    """
    
    wait_time = between(2, 5)  # Wait 2-5 seconds between tasks
    
    def on_start(self):
        """Called when a user starts."""
        self.pending_jobs = []
        self.completed_jobs = []
    
    @task(10)
    def create_job_flow(self):
        """
        Full flow: generate test video -> create job.
        This is the most common operation (weight 10).
        """
        # Step 1: Generate test video (server-side)
        video_sizes = [1, 5, 10, 20]  # MB
        video_size = random.choice(video_sizes)
        
        with self.client.post(
            f"/load-test/generate?size_mb={video_size}",
            name="/load-test/generate",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                object_path = data.get("object_path")
                
                # Step 2: Create conversion job
                output_formats = ['mp4', 'webm', 'avi', 'mp3']
                output_format = random.choice(output_formats)
                
                with self.client.post(
                    "/jobs",
                    json={"input_path": object_path, "output_format": output_format},
                    name="/jobs [create]",
                    catch_response=True
                ) as job_response:
                    if job_response.status_code == 200:
                        job_data = job_response.json()
                        job_id = job_data.get("id")
                        self.pending_jobs.append(job_id)
                        job_response.success()
                    else:
                        job_response.failure(f"Failed to create job: {job_response.text}")
                
                response.success()
            else:
                response.failure(f"Failed to generate test video: {response.text}")
    
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
                data = response.json()
                download_url = data.get("download_url")
                
                # Note: We don't actually download the file to avoid network overhead
                # Just getting the URL is enough to test the API
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
        # Generate test video
        response = self.client.post(
            "/load-test/generate?size_mb=5",
            name="/load-test/generate [burst]"
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
        print(f"❌ Request failed: {name} - {exception}")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when load test starts."""
    print("=" * 60)
    print("🚀 Video Processing Load Test Started (External Mode)")
    print("=" * 60)
    print(f"📍 Target: {environment.host}")
    if isinstance(environment.runner, MasterRunner):
        print(f"🔀 Running in distributed mode with {environment.runner.worker_count} workers")
    print("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops."""
    print("=" * 60)
    print("✅ Video Processing Load Test Completed")
    print("=" * 60)
    
    # Print summary stats
    stats = environment.stats
    print(f"📊 Total Requests: {stats.total.num_requests}")
    print(f"❌ Total Failures: {stats.total.num_failures}")
    print(f"⏱️  Average Response Time: {stats.total.avg_response_time:.2f}ms")
    print(f"📈 Requests/sec: {stats.total.total_rps:.2f}")
    print("=" * 60)
