import requests
import time
import subprocess

API_URL = "http://localhost/api"

print("="*60)
print("HPA Test - Generating Load to Trigger Autoscaling")
print("="*60)

# Check initial state
print("\n1. Current State:")
result = subprocess.run(
    ["kubectl", "get", "pods", "-n", "video-processing", "-l", "app=worker"],
    capture_output=True, text=True
)
print(result.stdout)

result = subprocess.run(
    ["kubectl", "get", "hpa", "-n", "video-processing"],
    capture_output=True, text=True
)
print(result.stdout)

# Create 30 jobs to trigger autoscaling
print("\n2. Creating 30 jobs to queue them in RabbitMQ...")
print("   (This should trigger worker scaling from 1 -> multiple pods)")

for i in range(30):
    try:
        # Request upload URL
        resp = requests.post(f"{API_URL}/upload/request", json={"filename": f"test_{i}.mp4"})
        if resp.status_code == 200:
            data = resp.json()
            
            # Create a job (this queues it in RabbitMQ)
            job_payload = {
                "input_path": data["object_path"],
                "output_format": "mp4"
            }
            job_resp = requests.post(f"{API_URL}/jobs", json=job_payload)
            if job_resp.status_code == 200:
                print(f"   ✓ Job {i+1}/30 created")
            else:
                print(f"   ✗ Job {i+1}/30 failed: {job_resp.status_code}")
        
        time.sleep(0.2)  # Small delay to avoid overwhelming the API
    except Exception as e:
        print(f"   ✗ Job {i+1}/30 error: {e}")

print("\n3. Waiting for KEDA to detect queue depth and scale workers...")
print("   (KEDA polls every 10s, scaling should start soon)")

# Monitor for 2 minutes
for iteration in range(12):  # 12 x 10s = 2 minutes
    time.sleep(10)
    
    result = subprocess.run(
        ["kubectl", "get", "pods", "-n", "video-processing", "-l", "app=worker", "--no-headers"],
        capture_output=True, text=True
    )
    worker_count = len([line for line in result.stdout.strip().split('\n') if line])
    
    result = subprocess.run(
        ["kubectl", "get", "hpa", "-n", "video-processing", "--no-headers"],
        capture_output=True, text=True
    )
    hpa_status = result.stdout.strip()
    
    print(f"\n   [{iteration+1}/12] Workers: {worker_count} | HPA: {hpa_status}")

print("\n" + "="*60)
print("HPA Test Complete!")
print("="*60)
print("\nFinal State:")
result = subprocess.run(
    ["kubectl", "get", "pods", "-n", "video-processing", "-l", "app=worker"],
    capture_output=True, text=True
)
print(result.stdout)
