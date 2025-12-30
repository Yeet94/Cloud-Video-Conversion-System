#!/usr/bin/env python3
"""
Fault Tolerance Testing Scripts for Cloud Video Conversion System
Tests: Pod termination, Network latency, CPU pressure
"""

import subprocess
import sys
import time
import argparse
import random

def run_cmd(cmd, check=True):
    """Run a shell command"""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, check=check)
    return result

def get_worker_pods():
    """Get list of worker pod names"""
    result = run_cmd([
        "kubectl", "get", "pods", "-n", "video-processing",
        "-l", "app=worker", "-o", "jsonpath={.items[*].metadata.name}"
    ])
    return result.stdout.strip().split()

def test_pod_termination():
    """Test 1: Worker Pod Termination"""
    print("\n" + "="*60)
    print("FAULT TOLERANCE TEST 1: Worker Pod Termination")
    print("="*60)
    
    pods = get_worker_pods()
    if not pods or pods == ['']:
        print("No worker pods found!")
        return
    
    target_pod = random.choice(pods)
    print(f"Target pod: {target_pod}")
    
    # Get current job count
    print("\n1. Checking current state...")
    run_cmd(["kubectl", "get", "pods", "-n", "video-processing", "-l", "app=worker"])
    
    # Delete the pod
    print(f"\n2. Terminating pod {target_pod}...")
    run_cmd(["kubectl", "delete", "pod", target_pod, "-n", "video-processing"])
    
    # Wait and observe
    print("\n3. Waiting for new pod to start...")
    time.sleep(10)
    
    print("\n4. New state:")
    run_cmd(["kubectl", "get", "pods", "-n", "video-processing", "-l", "app=worker"])
    
    # Check for requeued messages
    print("\n5. Check RabbitMQ queue (jobs should be requeued):")
    print("   kubectl port-forward svc/rabbitmq 15672:15672 -n video-processing")
    print("   Visit http://localhost:15672 and check queue depth")
    
    print("\n✅ Test complete! Verify:")
    print("   - New pod started automatically")
    print("   - Jobs were requeued (no loss)")
    print("   - System recovered within 20s")

def test_network_latency():
    """Test 2: Network Latency Injection"""
    print("\n" + "="*60)
    print("FAULT TOLERANCE TEST 2: Network Latency to MinIO")
    print("="*60)
    
    pods = get_worker_pods()
    if not pods or pods == ['']:
        print("No worker pods found!")
        return
    
    target_pod = random.choice(pods)
    print(f"Target pod: {target_pod}")
    
    print("\n1. Injecting 500ms latency to MinIO...")
    run_cmd([
        "kubectl", "exec", target_pod, "-n", "video-processing", "--",
        "tc", "qdisc", "add", "dev", "eth0", "root", "netem", "delay", "500ms"
    ], check=False)
    
    print("\n2. Latency injected! Jobs will be slower on this worker.")
    print("   Monitor conversion times in Grafana")
    
    print("\n3. Waiting 60 seconds...")
    time.sleep(60)
    
    print("\n4. Removing latency...")
    run_cmd([
        "kubectl", "exec", target_pod, "-n", "video-processing", "--",
        "tc", "qdisc", "del", "dev", "eth0", "root"
    ], check=False)
    
    print("\n✅ Test complete! Verify:")
    print("   - No job failures (just slower)")
    print("   - P95/P99 latency increased during test")
    print("   - System recovered after latency removed")

def test_cpu_pressure():
    """Test 3: CPU Pressure"""
    print("\n" + "="*60)
    print("FAULT TOLERANCE TEST 3: CPU Pressure")
    print("="*60)
    
    pods = get_worker_pods()
    if not pods or pods == ['']:
        print("No worker pods found!")
        return
    
    target_pod = random.choice(pods)
    print(f"Target pod: {target_pod}")
    
    print("\n1. Applying CPU stress (80% load for 60s)...")
    
    # Start stress in background
    stress_cmd = [
        "kubectl", "exec", target_pod, "-n", "video-processing", "--",
        "stress-ng", "--cpu", "2", "--cpu-load", "80", "--timeout", "60s"
    ]
    
    print("   Starting stress-ng...")
    subprocess.Popen(stress_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    print("\n2. CPU stress applied! Monitor worker CPU in Grafana")
    print("   Conversion times will increase")
    
    print("\n3. Waiting for stress to complete (60s)...")
    time.sleep(65)
    
    print("\n✅ Test complete! Verify:")
    print("   - Jobs completed despite CPU pressure (slower)")
    print("   - No job failures")
    print("   - CPU usage spiked to ~80%")
    print("   - System recovered after stress ended")

def monitor_dashboard():
    """Helper to display monitoring commands"""
    print("\n" + "="*60)
    print("MONITORING COMMANDS")
    print("="*60)
    print("\nGrafana Dashboard:")
    print("  kubectl port-forward svc/prometheus-grafana 3000:80 -n monitoring")
    print("  http://localhost:3000 (admin/admin)")
    print("\nRabbitMQ Management:")
    print("  kubectl port-forward svc/rabbitmq 15672:15672 -n video-processing")
    print("  http://localhost:15672 (guest/guest)")
    print("\nWatch Worker Pods:")
    print("  kubectl get pods -n video-processing -l app=worker -w")
    print("\nWatch HPA:")
    print("  kubectl get hpa -n video-processing -w")

def main():
    parser = argparse.ArgumentParser(description="Fault Tolerance Testing")
    parser.add_argument("test", choices=["pod-kill", "network-latency", "cpu-pressure", "all"],
                       help="Test to run")
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("Cloud Video Conversion - Fault Tolerance Testing")
    print("="*60)
    print("\n⚠️  WARNING: These tests will inject faults into your cluster!")
    print("Make sure you have monitoring ready (Grafana dashboard)")
    print("\nPress Ctrl+C to cancel, or wait 5 seconds to continue...")
    
    try:
        time.sleep(5)
    except KeyboardInterrupt:
        print("\n\nCancelled.")
        sys.exit(0)
    
    if args.test == "pod-kill" or args.test == "all":
        test_pod_termination()
    
    if args.test == "network-latency" or args.test == "all":
        if args.test == "all":
            time.sleep(30)  # Wait between tests
        test_network_latency()
    
    if args.test == "cpu-pressure" or args.test == "all":
        if args.test == "all":
            time.sleep(30)  # Wait between tests
        test_cpu_pressure()
    
    monitor_dashboard()
    
    print("\n" + "="*60)
    print("All tests complete!")
    print("="*60)

if __name__ == "__main__":
    main()
