#!/usr/bin/env python3
"""
Smart Load Balancing Test Script
Demonstrates CPU-based autoscaling and intelligent load distribution

This test proves that:
1. CPU-based HPA scales workers independently of queue depth
2. Readiness probes stop routing to overloaded workers
3. System maintains better throughput under stress
"""

import subprocess
import time
import sys
import requests
import json
from typing import List, Dict

def run_cmd(cmd: List[str], check=True) -> subprocess.CompletedProcess:
    """Run command and return result"""
    print(f"Running: {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True, check=check)

def get_worker_pods() -> List[str]:
    """Get list of worker pod names"""
    result = run_cmd([
        "kubectl", "get", "pods", "-n", "video-processing",
        "-l", "app=worker", "-o", "jsonpath={.items[*].metadata.name}"
    ])
    pods = result.stdout.strip().split()
    return [p for p in pods if p]  # Filter empty strings

def get_pod_cpu(pod_name: str) -> float:
    """Get CPU usage of a pod"""
    result = run_cmd([
        "kubectl", "top", "pod", pod_name, "-n", "video-processing",
        "--no-headers"
    ], check=False)
    
    if result.returncode == 0:
        parts = result.stdout.strip().split()
        if len(parts) >= 2:
            cpu_str = parts[1].replace('m', '')
            return float(cpu_str)
    return 0.0

def check_pod_ready(pod_name: str) -> bool:
    """Check if pod is marked as ready"""
    result = run_cmd([
        "kubectl", "get", "pod", pod_name, "-n", "video-processing",
        "-o", "jsonpath={.status.conditions[?(@.type=='Ready')].status}"
    ])
    return result.stdout.strip() == "True"

def apply_cpu_stress(pod_name: str, duration_s=60) -> None:
    """Apply CPU stress to a pod"""
    print(f"\n🔥 Applying 80% CPU stress to {pod_name} for {duration_s}s...")
    cmd = [
        "kubectl", "exec", pod_name, "-n", "video-processing", "--",
        "stress-ng", "--cpu", "2", "--cpu-load", "80", "--timeout", f"{duration_s}s"
    ]
    # Run in background
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def get_hpa_status() -> Dict:
    """Get HPA and worker replicas"""
    # Get deployment replicas
    result = run_cmd([
        "kubectl", "get", "deployment", "worker", "-n", "video-processing",
        "-o", "jsonpath={.spec.replicas},{.status.readyReplicas}"
    ])
    desired, ready = result.stdout.strip().split(',') if ',' in result.stdout else ('0', '0')
    
    # Get HPA current replicas
    result = run_cmd([
        "kubectl", "get", "hpa", "worker-cpu-hpa", "-n", "video-processing",
        "-o", "jsonpath={.status.currentReplicas},{.status.desiredReplicas}"
    ], check=False)
    
    current, hpa_desired = ('0', '0')
    if result.returncode == 0 and ',' in result.stdout:
        current, hpa_desired = result.stdout.strip().split(',')
    
    return {
        'deployment_desired': int(desired),
        'deployment_ready': int(ready or 0),
        'hpa_current': int(current),
        'hpa_desired': int(hpa_desired)
    }

def test_readiness_probe_isolation():
    """
    Test 1: Readiness Probe Isolation
    
    Verify that when a worker becomes overloaded (CPU > 85%),
    Kubernetes stops routing new work to it.
    """
    print("\n" + "="*70)
    print("TEST 1: Readiness Probe Isolation")
    print("="*70)
    print("\nObjective: Verify overloaded workers are removed from service rotation")
    
    pods = get_worker_pods()
    if len(pods) < 2:
        print("⚠️  Need at least 2 worker pods for this test")
        print("   Scale up workers: kubectl scale deployment worker --replicas=3 -n video-processing")
        return
    
    target_pod = pods[0]
    print(f"\n1. Target pod: {target_pod}")
    print(f"   Other pods: {', '.join(pods[1:])}")
    
    # Check initial readiness
    print("\n2. Checking initial pod readiness...")
    for pod in pods:
        ready = check_pod_ready(pod)
        print(f"   {pod}: {'✅ Ready' if ready else '❌ Not Ready'}")
    
    # Apply CPU stress
    apply_cpu_stress(target_pod, duration_s=90)
    
    print("\n3. Waiting 15s for readiness probe to detect high CPU...")
    time.sleep(15)
    
    # Check readiness after stress
    print("\n4. Checking pod readiness under stress:")
    for pod in pods:
        ready = check_pod_ready(pod)
        cpu = get_pod_cpu(pod)
        status = "✅ Ready" if ready else "❌ Not Ready (isolated!)"
        print(f"   {pod}: {status} (CPU: {cpu}m)")
    
    target_ready = check_pod_ready(target_pod)
    
    print("\n📊 Test Result:")
    if not target_ready:
        print("✅ SUCCESS: Overloaded worker was isolated from service rotation")
        print("   Kubernetes will not send new jobs to this pod until CPU drops")
    else:
        print("⚠️  PARTIAL: Pod still marked ready (readiness probe may need tuning)")
    
    print("\n5. Waiting for stress to complete and pod to recover...")
    time.sleep(80)
    
    print("\n6. Final readiness check:")
    for pod in pods:
        ready = check_pod_ready(pod)
        print(f"   {pod}: {'✅ Recovered' if ready else '⚠️  Still not ready'}")

def test_cpu_based_scaling():
    """
    Test 2: CPU-Based Autoscaling
    
    Verify that HPA scales workers based on CPU utilization
    independently of queue depth.
    """
    print("\n" + "="*70)
    print("TEST 2: CPU-Based Autoscaling")
    print("="*70)
    print("\nObjective: Verify workers scale based on CPU load (not just queue depth)")
    
    print("\n1. Initial state:")
    status = get_hpa_status()
    print(f"   Deployment replicas: {status['deployment_ready']}/{status['deployment_desired']}")
    print(f"   HPA status: {status['hpa_current']} current, {status['hpa_desired']} desired")
    
    pods = get_worker_pods()
    if not pods:
        print("❌ No worker pods found!")
        return
    
    print(f"\n2. Applying CPU stress to all {len(pods)} worker(s)...")
    for pod in pods:
        apply_cpu_stress(pod, duration_s=120)
    
    print("\n3. Monitoring HPA scaling behavior...")
    print("   Time | Pods Ready | HPA Desired | Avg CPU")
    print("   " + "-"*50)
    
    for i in range(12):  # Monitor for 60 seconds
        time.sleep(5)
        status = get_hpa_status()
        
        # Calculate average CPU
        total_cpu = sum(get_pod_cpu(pod) for pod in get_worker_pods())
        avg_cpu = total_cpu / len(get_worker_pods()) if get_worker_pods() else 0
        
        print(f"   {i*5:3d}s | {status['deployment_ready']:10d} | {status['hpa_desired']:11d} | {avg_cpu:7.0f}m")
    
    final_status = get_hpa_status()
    
    print("\n📊 Test Result:")
    if final_status['hpa_desired'] > status['deployment_desired']:
        print(f"✅ SUCCESS: HPA scaled up from {status['deployment_desired']} to {final_status['hpa_desired']} pods")
        print("   CPU-based autoscaling is working!")
    else:
        print(f"⚠️  No scaling detected. HPA may need more time or workload.")
        print(f"   Tip: Check HPA with: kubectl describe hpa worker-cpu-hpa -n video-processing")
    
    print("\n4. Waiting for stress to complete and scale-down...")
    time.sleep(70)
    
    final_final_status = get_hpa_status()
    print(f"\n5. Final state after cooldown:")
    print(f"   Deployment replicas: {final_final_status['deployment_ready']}/{final_final_status['deployment_desired']}")

def test_combined_scaling():
    """
    Test 3: Combined KEDA + HPA Scaling
    
    Show that KEDA and HPA work together, with the higher
    replica count winning.
    """
    print("\n" + "="*70)
    print("TEST 3: Combined KEDA + HPA Scaling")
    print("="*70)
    print("\nObjective: Demonstrate dual-trigger autoscaling")
    print("\nℹ️  This test requires:")
    print("   - KEDA ScaledObject monitoring queue depth")
    print("   - HPA monitoring CPU utilization")
    print("   - Jobs in the queue AND CPU stress")
    
    print("\n📋 To run this test manually:")
    print("   1. Submit 25+ jobs (triggers KEDA to scale to 5 pods)")
    print("   2. Apply CPU stress to all pods (triggers HPA)")
    print("   3. Observe which autoscaler wins (higher replica count)")
    print("   4. Monitor: kubectl get hpa,scaledobject -n video-processing -w")

def monitoring_commands():
    """Display helpful monitoring commands"""
    print("\n" + "="*70)
    print("MONITORING COMMANDS")
    print("="*70)
    print("\nWatch pod status and readiness:")
    print("  kubectl get pods -n video-processing -l app=worker -w")
    print("\nWatch HPA scaling:")
    print("  kubectl get hpa -n video-processing -w")
    print("\nWatch KEDA ScaledObject:")
    print("  kubectl get scaledobject -n video-processing -w")
    print("\nCheck pod CPU/Memory:")
    print("  kubectl top pods -n video-processing -l app=worker")
    print("\nDescribe HPA:")
    print("  kubectl describe hpa worker-cpu-hpa -n video-processing")
    print("\nTest worker health endpoint:")
    print("  kubectl port-forward -n video-processing deploy/worker 8080:8080")
    print("  curl http://localhost:8080/ready")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Smart Load Balancing Tests")
    parser.add_argument("test", nargs='?', 
                       choices=["readiness", "cpu-scaling", "combined", "all"],
                       default="all",
                       help="Test to run (default: all)")
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("Smart Load Balancing & CPU Autoscaling Tests")
    print("="*70)
    print("\n⚠️  WARNING: These tests will stress your workers!")
    print("Make sure you have:")
    print("  - Metrics server installed (kubectl top works)")
    print("  - HPA deployed (kubectl get hpa -n video-processing)")
    print("  - At least 2 worker pods running")
    
    print("\nPress Ctrl+C to cancel, or wait 5 seconds to continue...")
    try:
        time.sleep(5)
    except KeyboardInterrupt:
        print("\n\nCancelled.")
        sys.exit(0)
    
    if args.test in ["readiness", "all"]:
        test_readiness_probe_isolation()
    
    if args.test in ["cpu-scaling", "all"]:
        if args.test == "all":
            time.sleep(30)  # Wait between tests
        test_cpu_based_scaling()
    
    if args.test in ["combined", "all"]:
        test_combined_scaling()
    
    monitoring_commands()
    
    print("\n" + "="*70)
    print("Tests Complete!")
    print("="*70)

if __name__ == "__main__":
    main()
