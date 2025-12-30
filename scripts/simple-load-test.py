#!/usr/bin/env python3
"""
Simple Load Generator - Creates dummy video files without FFmpeg
"""
import os
import requests
import time
import random

def create_dummy_video(filename, size_mb):
    """Create a dummy MP4 file of specified size"""
    size_bytes = size_mb * 1024 * 1024
    
    # Minimal valid MP4 header
    mp4_header = bytes([
        0x00, 0x00, 0x00, 0x20, 0x66, 0x74, 0x79, 0x70,
        0x69, 0x73, 0x6F, 0x6D, 0x00, 0x00, 0x02, 0x00,
        0x69, 0x73, 0x6F, 0x6D, 0x69, 0x73, 0x6F, 0x32,
        0x6D, 0x70, 0x34, 0x31, 0x00, 0x00, 0x00, 0x08
    ])
    
    print(f"Creating {size_mb}MB dummy video: {filename}")
    with open(filename, 'wb') as f:
        f.write(mp4_header)
        remaining = size_bytes - len(mp4_header)
        # Fill with random data in chunks
        chunk_size = 1024 * 1024  # 1MB chunks
        while remaining > 0:
            chunk = min(chunk_size, remaining)
            f.write(os.urandom(chunk))
            remaining -= chunk
    
    print(f"✓ Created {filename} ({size_mb}MB)")
    return filename

def upload_and_convert(api_url, video_path, job_num):
    """Upload a video and create conversion job"""
    try:
        # Step 1: Request upload URL
        resp = requests.post(f"{api_url}/upload/request", 
                           json={"filename": f"test_video_{job_num}.mp4"})
        if resp.status_code != 200:
            return {"status": "failed", "error": "Failed to get upload URL"}
        
        data = resp.json()
        upload_url = data["upload_url"]
        object_path = data["object_path"]
        
        # Step 2: Upload video
        with open(video_path, 'rb') as f:
            video_data = f.read()
            resp = requests.put(upload_url, data=video_data)
            if resp.status_code not in [200, 201]:
                return {"status": "failed", "error": "Upload failed"}
        
        # Step 3: Create conversion job
        job_payload = {
            "input_path": object_path,
            "output_format": "mp4"
        }
        resp = requests.post(f"{api_url}/jobs", json=job_payload)
        if resp.status_code != 200:
            return {"status": "failed", "error": "Job creation failed"}
        
        job_data = resp.json()
        return {
            "status": "success",
            "job_id": job_data.get("job_id")
        }
    except Exception as e:
        return {"status": "failed", "error": str(e)}

def run_load_test(api_url, video_size_mb, num_jobs):
    """Run load test with specified video size"""
    print("\n" + "="*60)
    print(f"Load Test: {num_jobs} jobs with {video_size_mb}MB videos")
    print("="*60)
    
    # Create test video
    video_filename = f"test_video_{video_size_mb}mb.mp4"
    if not os.path.exists(video_filename):
        create_dummy_video(video_filename, video_size_mb)
    
    # Run tests
    results = []
    start_time = time.time()
    
    for i in range(num_jobs):
        print(f"Submitting job {i+1}/{num_jobs}...", end=" ")
        result = upload_and_convert(api_url, video_filename, i)
        
        if result["status"] == "success":
            print(f"✓ Job {result['job_id']}")
        else:
            print(f"✗ {result['error']}")
        
        results.append(result)
        time.sleep(0.1)  # Small delay between jobs
    
    elapsed = time.time() - start_time
    successful = len([r for r in results if r["status"] == "success"])
    
    print("\n" + "="*60)
    print("Results:")
    print(f"  Video Size: {video_size_mb}MB")
    print(f"  Jobs Submitted: {num_jobs}")
    print(f"  Successful: {successful}")
    print(f"  Failed: {num_jobs - successful}")
    print(f"  Time: {elapsed:.2f}s")
    print(f"  Throughput: {num_jobs/elapsed:.2f} jobs/s")
    print("="*60)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Simple Load Generator")
    parser.add_argument("--api-url", default="http://localhost/api", 
                       help="API URL")
    parser.add_argument("--video-size", type=int, default=10,
                       help="Video size in MB (10, 50, or 100)")
    parser.add_argument("--jobs", type=int, default=20,
                       help="Number of jobs to submit")
    
    args = parser.parse_args()
    
    run_load_test(args.api_url, args.video_size, args.jobs)
