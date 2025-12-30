#!/usr/bin/env python3
"""
Load Generator for Cloud Video Conversion System
Generates test videos and submits conversion jobs to test autoscaling
"""

import asyncio
import aiohttp
import time
import os
import sys
import argparse
from typing import List, Dict
import json
import subprocess
import random

class LoadGenerator:
    def __init__(self, api_url: str, num_jobs: int, concurrent: int, video_size_mb: int):
        self.api_url = api_url.rstrip('/')
        self.num_jobs = num_jobs
        self.concurrent = concurrent
        self.video_size_mb = video_size_mb
        self.results = []
        
    def create_test_video(self, filename: str, size_mb: int) -> str:
        """Create a test video file using FFmpeg"""
        duration = max(1, size_mb // 2)  # Rough approximation
        
        cmd = [
            'ffmpeg', '-f', 'lavfi', '-i', 
            f'color=c=blue:s=1280x720:d={duration}',
            '-f', 'lavfi', '-i', 
            f'sine=frequency=1000:duration={duration}',
            '-pix_fmt', 'yuv420p',
            '-c:v', 'libx264', '-preset', 'fast',
            '-b:v', f'{size_mb}M',
            '-c:a', 'aac',
            '-y', filename
        ]
        
        print(f"Creating {size_mb}MB test video: {filename}")
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return filename
    
    async def submit_job(self, session: aiohttp.ClientSession, job_id: int, video_path: str) -> Dict:
        """Submit a single video conversion job"""
        start_time = time.time()
        
        try:
            # Step 1: Request upload URL
            filename = os.path.basename(video_path)
            async with session.post(f"{self.api_url}/upload/request", json={"filename": filename}) as resp:
                if resp.status != 200:
                    return {"job_id": job_id, "status": "failed", "error": "Failed to get upload URL"}
                data = await resp.json()
                upload_url = data["upload_url"]
                file_key = data.get("file_key") or data.get("object_path")
            
            # Step 2: Upload video to MinIO
            with open(video_path, 'rb') as f:
                video_data = f.read()
                async with session.put(upload_url, data=video_data) as resp:
                    if resp.status not in [200, 201]:
                        return {"job_id": job_id, "status": "failed", "error": "Upload failed"}
            
            # Step 3: Create conversion job
            job_payload = {
                "input_path": file_key,
                "output_format": "mp4"
            }
            async with session.post(f"{self.api_url}/jobs", json=job_payload) as resp:
                if resp.status != 200:
                    return {"job_id": job_id, "status": "failed", "error": "Job creation failed"}
                job_data = await resp.json()
            
            elapsed = time.time() - start_time
            return {
                "job_id": job_id,
                "api_job_id": job_data.get("job_id"),
                "status": "submitted",
                "elapsed": elapsed
            }
            
        except Exception as e:
            return {"job_id": job_id, "status": "failed", "error": str(e)}
    
    async def run_batch(self, video_path: str):
        """Run a batch of concurrent job submissions"""
        async with aiohttp.ClientSession() as session:
            tasks = []
            for i in range(self.num_jobs):
                task = self.submit_job(session, i, video_path)
                tasks.append(task)
                
                # Control concurrency
                if len(tasks) >= self.concurrent:
                    results = await asyncio.gather(*tasks)
                    self.results.extend(results)
                    tasks = []
                    
            # Submit remaining tasks
            if tasks:
                results = await asyncio.gather(*tasks)
                self.results.extend(results)
    
    async def monitor_metrics(self):
        """Monitor queue depth and worker count"""
        print("\n" + "="*60)
        print("Monitoring Metrics (Ctrl+C to stop)")
        print("="*60)
        
        try:
            while True:
                # Get pod count
                result = subprocess.run(
                    ["kubectl", "get", "pods", "-n", "video-processing", 
                     "-l", "app=worker", "--no-headers"],
                    capture_output=True, text=True
                )
                worker_count = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0
                
                # Get HPA status
                result = subprocess.run(
                    ["kubectl", "get", "hpa", "-n", "video-processing", "--no-headers"],
                    capture_output=True, text=True
                )
                hpa_info = result.stdout.strip()
                
                print(f"\rWorkers: {worker_count} | {hpa_info}", end='', flush=True)
                await asyncio.sleep(2)
                
        except KeyboardInterrupt:
            print("\n\nMonitoring stopped")
    
    def print_summary(self):
        """Print load test summary"""
        successful = [r for r in self.results if r["status"] == "submitted"]
        failed = [r for r in self.results if r["status"] == "failed"]
        
        print("\n" + "="*60)
        print("Load Test Summary")
        print("="*60)
        print(f"Total Jobs: {self.num_jobs}")
        print(f"Successful: {len(successful)}")
        print(f"Failed: {len(failed)}")
        
        if successful:
            avg_time = sum(r["elapsed"] for r in successful) / len(successful)
            print(f"Average Submission Time: {avg_time:.2f}s")
        
        print("\nCheck Grafana dashboard for detailed metrics!")
        print("kubectl port-forward svc/prometheus-grafana 3000:80 -n monitoring")

def main():
    parser = argparse.ArgumentParser(description="Load Generator for Video Conversion System")
    parser.add_argument("--api-url", default="http://localhost:8000", 
                       help="API URL (default: http://localhost:8000)")
    parser.add_argument("--jobs", type=int, default=50, 
                       help="Number of jobs to generate (default: 50)")
    parser.add_argument("--concurrent", type=int, default=5, 
                       help="Concurrent job submissions (default: 5)")
    parser.add_argument("--video-size", type=int, default=10, 
                       help="Video size in MB (default: 10)")
    parser.add_argument("--monitor", action="store_true", 
                       help="Monitor metrics after submission")
    
    args = parser.parse_args()
    
    # Create test video
    video_path = f"test_video_{args.video_size}mb.mp4"
    if not os.path.exists(video_path):
        generator = LoadGenerator(args.api_url, args.jobs, args.concurrent, args.video_size)
        generator.create_test_video(video_path, args.video_size)
    
    # Run load test
    generator = LoadGenerator(args.api_url, args.jobs, args.concurrent, args.video_size)
    
    print(f"\n{'='*60}")
    print(f"Starting Load Test")
    print(f"{'='*60}")
    print(f"API URL: {args.api_url}")
    print(f"Jobs: {args.jobs}")
    print(f"Concurrent: {args.concurrent}")
    print(f"Video Size: {args.video_size}MB")
    print(f"{'='*60}\n")
    
    start = time.time()
    asyncio.run(generator.run_batch(video_path))
    elapsed = time.time() - start
    
    generator.print_summary()
    print(f"\nTotal Time: {elapsed:.2f}s")
    print(f"Throughput: {args.jobs/elapsed:.2f} jobs/sec")
    
    if args.monitor:
        asyncio.run(generator.monitor_metrics())

if __name__ == "__main__":
    main()
