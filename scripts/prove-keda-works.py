#!/usr/bin/env python3
"""
KEDA Autoscaling Proof Script
==============================
This script provides visual, real-time proof that KEDA is working by:
1. Monitoring initial worker count (should be 0 or minReplicaCount)
2. Submitting jobs to create queue backlog
3. Watching KEDA scale workers up based on queue depth
4. Monitoring queue drain and worker scale-down

Usage:
    python prove-keda-works.py --api-url http://localhost:8000 --num-jobs 50
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

import requests
from colorama import Fore, Style, init

# Initialize colorama for colored terminal output
init(autoreset=True)


class KEDAProofMonitor:
    """Monitor and prove KEDA autoscaling behavior."""
    
    def __init__(self, api_url: str, namespace: str = "default"):
        self.api_url = api_url.rstrip('/')
        self.namespace = namespace
        self.start_time = None
        self.events = []
        
    def print_header(self, text: str):
        """Print a formatted header."""
        print(f"\n{Fore.CYAN}{'=' * 80}")
        print(f"{Fore.CYAN}{text.center(80)}")
        print(f"{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}\n")
        
    def print_status(self, label: str, value: str, color=Fore.WHITE):
        """Print a status line."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"{Fore.YELLOW}[{timestamp}]{Style.RESET_ALL} {label}: {color}{value}{Style.RESET_ALL}")
        
    def get_worker_count(self) -> int:
        """Get current number of worker pods."""
        try:
            result = subprocess.run(
                ["kubectl", "get", "pods", "-n", self.namespace, 
                 "-l", "app=video-worker", "-o", "json"],
                capture_output=True,
                text=True,
                check=True
            )
            pods = json.loads(result.stdout)
            # Count only Running or Pending pods (not Terminating)
            active_pods = [
                p for p in pods.get('items', [])
                if p.get('metadata', {}).get('deletionTimestamp') is None
            ]
            return len(active_pods)
        except subprocess.CalledProcessError as e:
            print(f"{Fore.RED}Error getting worker count: {e}{Style.RESET_ALL}")
            return -1
            
    def get_queue_depth(self) -> int:
        """Get RabbitMQ queue depth."""
        try:
            result = subprocess.run(
                ["kubectl", "exec", "-n", self.namespace, 
                 "deployment/rabbitmq", "--", 
                 "rabbitmqctl", "list_queues", "name", "messages"],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse output: "video_jobs\t25"
            for line in result.stdout.strip().split('\n'):
                if 'video_jobs' in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1])
            return 0
        except (subprocess.CalledProcessError, ValueError) as e:
            print(f"{Fore.RED}Error getting queue depth: {e}{Style.RESET_ALL}")
            return -1
            
    def get_keda_scaledobject_status(self) -> Optional[Dict]:
        """Get KEDA ScaledObject status."""
        try:
            result = subprocess.run(
                ["kubectl", "get", "scaledobject", "-n", self.namespace, 
                 "-o", "json"],
                capture_output=True,
                text=True,
                check=True
            )
            data = json.loads(result.stdout)
            if data.get('items'):
                return data['items'][0].get('status', {})
            return None
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            print(f"{Fore.RED}Error getting KEDA status: {e}{Style.RESET_ALL}")
            return None
            
    def submit_test_job(self, job_number: int) -> bool:
        """Submit a single test job."""
        try:
            # Request upload URL
            response = requests.post(
                f"{self.api_url}/upload/request",
                json={
                    "filename": f"test_video_{job_number}.mp4",
                    "content_type": "video/mp4"
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            job_id = data['job_id']
            presigned_url = data['presigned_url']
            
            # Create a small dummy video file (1KB)
            dummy_data = b'\x00' * 1024
            
            # Upload to MinIO
            upload_response = requests.put(
                presigned_url,
                data=dummy_data,
                headers={'Content-Type': 'video/mp4'},
                timeout=10
            )
            upload_response.raise_for_status()
            
            # Create conversion job
            job_response = requests.post(
                f"{self.api_url}/jobs",
                json={
                    "job_id": job_id,
                    "output_format": "mp4"
                },
                timeout=10
            )
            job_response.raise_for_status()
            
            return True
            
        except requests.RequestException as e:
            print(f"{Fore.RED}Error submitting job {job_number}: {e}{Style.RESET_ALL}")
            return False
            
    def record_event(self, event_type: str, workers: int, queue: int, notes: str = ""):
        """Record a monitoring event."""
        elapsed = time.time() - self.start_time if self.start_time else 0
        event = {
            'timestamp': datetime.now().isoformat(),
            'elapsed_seconds': round(elapsed, 1),
            'event_type': event_type,
            'workers': workers,
            'queue_depth': queue,
            'notes': notes
        }
        self.events.append(event)
        
    def print_monitoring_line(self, workers: int, queue: int, expected_workers: int):
        """Print a single monitoring line."""
        elapsed = time.time() - self.start_time if self.start_time else 0
        
        # Color code based on whether workers match expected
        if workers == expected_workers:
            worker_color = Fore.GREEN
            status = "✓"
        elif workers < expected_workers:
            worker_color = Fore.YELLOW
            status = "↑"  # Scaling up
        else:
            worker_color = Fore.YELLOW
            status = "↓"  # Scaling down
            
        print(
            f"{Fore.YELLOW}[{elapsed:6.1f}s]{Style.RESET_ALL} "
            f"Queue: {Fore.CYAN}{queue:3d}{Style.RESET_ALL} | "
            f"Workers: {worker_color}{workers:2d}{Style.RESET_ALL} | "
            f"Expected: {Fore.MAGENTA}{expected_workers:2d}{Style.RESET_ALL} | "
            f"{status}"
        )
        
    def calculate_expected_workers(self, queue_depth: int, 
                                   target_per_worker: int = 5,
                                   min_replicas: int = 0,
                                   max_replicas: int = 10) -> int:
        """Calculate expected worker count based on KEDA formula."""
        if queue_depth == 0:
            return min_replicas
        
        desired = (queue_depth + target_per_worker - 1) // target_per_worker  # Ceiling division
        return max(min_replicas, min(desired, max_replicas))
        
    def run_proof(self, num_jobs: int = 50, 
                  target_per_worker: int = 5,
                  min_replicas: int = 0,
                  max_replicas: int = 10):
        """Run the complete KEDA proof demonstration."""
        
        self.start_time = time.time()
        
        # ============================================================
        # PHASE 1: Initial State
        # ============================================================
        self.print_header("PHASE 1: Initial State (Before Load)")
        
        initial_workers = self.get_worker_count()
        initial_queue = self.get_queue_depth()
        
        self.print_status("Initial Worker Count", str(initial_workers), Fore.GREEN)
        self.print_status("Initial Queue Depth", str(initial_queue), Fore.GREEN)
        
        if initial_workers == -1 or initial_queue == -1:
            print(f"{Fore.RED}Failed to get initial metrics. Is Kubernetes running?{Style.RESET_ALL}")
            return False
            
        self.record_event("initial_state", initial_workers, initial_queue, 
                         "System idle, workers should be at minimum")
        
        print(f"\n{Fore.GREEN}✓ Baseline established{Style.RESET_ALL}")
        time.sleep(2)
        
        # ============================================================
        # PHASE 2: Job Submission
        # ============================================================
        self.print_header(f"PHASE 2: Submitting {num_jobs} Jobs")
        
        print(f"{Fore.CYAN}Submitting jobs rapidly to create queue backlog...{Style.RESET_ALL}\n")
        
        successful_jobs = 0
        for i in range(num_jobs):
            if self.submit_test_job(i + 1):
                successful_jobs += 1
                if (i + 1) % 10 == 0:
                    print(f"{Fore.GREEN}✓ Submitted {i + 1}/{num_jobs} jobs{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}✗ Failed to submit job {i + 1}{Style.RESET_ALL}")
                
        print(f"\n{Fore.GREEN}✓ Successfully submitted {successful_jobs}/{num_jobs} jobs{Style.RESET_ALL}")
        
        # Check queue immediately after submission
        time.sleep(2)
        post_submit_queue = self.get_queue_depth()
        post_submit_workers = self.get_worker_count()
        
        self.print_status("Queue Depth After Submission", str(post_submit_queue), Fore.CYAN)
        self.print_status("Workers After Submission", str(post_submit_workers), Fore.CYAN)
        
        self.record_event("jobs_submitted", post_submit_workers, post_submit_queue,
                         f"{successful_jobs} jobs submitted")
        
        # ============================================================
        # PHASE 3: KEDA Scale-Up Monitoring
        # ============================================================
        self.print_header("PHASE 3: Monitoring KEDA Scale-Up")
        
        print(f"{Fore.CYAN}Watching KEDA scale workers based on queue depth...{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Formula: Workers = ceil(Queue / {target_per_worker}), "
              f"Min={min_replicas}, Max={max_replicas}{Style.RESET_ALL}\n")
        
        max_workers_seen = post_submit_workers
        scale_up_complete = False
        monitoring_duration = 120  # Monitor for up to 2 minutes
        check_interval = 5
        
        for elapsed in range(0, monitoring_duration, check_interval):
            workers = self.get_worker_count()
            queue = self.get_queue_depth()
            expected = self.calculate_expected_workers(queue, target_per_worker, 
                                                      min_replicas, max_replicas)
            
            self.print_monitoring_line(workers, queue, expected)
            self.record_event("monitoring", workers, queue)
            
            if workers > max_workers_seen:
                max_workers_seen = workers
                print(f"{Fore.GREEN}  → KEDA scaled up to {workers} workers!{Style.RESET_ALL}")
                
            # Check if we've reached expected scale
            if workers >= expected and queue > 0:
                if not scale_up_complete:
                    scale_up_complete = True
                    print(f"{Fore.GREEN}  → Scale-up complete! Workers match expected count.{Style.RESET_ALL}")
                    
            # If queue is empty, break early
            if queue == 0:
                print(f"{Fore.GREEN}  → Queue drained!{Style.RESET_ALL}")
                break
                
            time.sleep(check_interval)
            
        # ============================================================
        # PHASE 4: Scale-Down Monitoring
        # ============================================================
        self.print_header("PHASE 4: Monitoring KEDA Scale-Down")
        
        print(f"{Fore.CYAN}Queue is empty. Watching KEDA scale workers back down...{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Note: KEDA has a cooldown period (typically 30-60s) before scaling down{Style.RESET_ALL}\n")
        
        scale_down_start = time.time()
        scale_down_complete = False
        
        for elapsed in range(0, 180, check_interval):  # Monitor for up to 3 minutes
            workers = self.get_worker_count()
            queue = self.get_queue_depth()
            expected = self.calculate_expected_workers(queue, target_per_worker,
                                                      min_replicas, max_replicas)
            
            self.print_monitoring_line(workers, queue, expected)
            self.record_event("scale_down_monitoring", workers, queue)
            
            if workers < max_workers_seen and not scale_down_complete:
                print(f"{Fore.YELLOW}  → KEDA scaling down... ({workers} workers){Style.RESET_ALL}")
                
            if workers == expected and workers == min_replicas:
                if not scale_down_complete:
                    scale_down_complete = True
                    scale_down_duration = time.time() - scale_down_start
                    print(f"{Fore.GREEN}  → Scale-down complete! Back to {min_replicas} workers "
                          f"after {scale_down_duration:.1f}s{Style.RESET_ALL}")
                    break
                    
            time.sleep(check_interval)
            
        # ============================================================
        # PHASE 5: Summary
        # ============================================================
        self.print_header("KEDA Proof Summary")
        
        final_workers = self.get_worker_count()
        final_queue = self.get_queue_depth()
        
        print(f"{Fore.CYAN}Initial State:{Style.RESET_ALL}")
        print(f"  Workers: {initial_workers}")
        print(f"  Queue:   {initial_queue}")
        
        print(f"\n{Fore.CYAN}Peak State:{Style.RESET_ALL}")
        print(f"  Max Workers: {max_workers_seen}")
        print(f"  Max Queue:   {post_submit_queue}")
        
        print(f"\n{Fore.CYAN}Final State:{Style.RESET_ALL}")
        print(f"  Workers: {final_workers}")
        print(f"  Queue:   {final_queue}")
        
        # Proof validation
        print(f"\n{Fore.CYAN}KEDA Proof Validation:{Style.RESET_ALL}")
        
        proofs = []
        
        # Proof 1: Workers scaled up
        if max_workers_seen > initial_workers:
            proofs.append(("✓", "Workers scaled UP from queue backlog", Fore.GREEN))
        else:
            proofs.append(("✗", "Workers did NOT scale up", Fore.RED))
            
        # Proof 2: Scaling followed formula
        expected_max = self.calculate_expected_workers(post_submit_queue, target_per_worker,
                                                       min_replicas, max_replicas)
        if abs(max_workers_seen - expected_max) <= 1:  # Allow 1 worker tolerance
            proofs.append(("✓", f"Scaling followed formula (expected ~{expected_max}, got {max_workers_seen})", 
                          Fore.GREEN))
        else:
            proofs.append(("✗", f"Scaling deviated from formula (expected {expected_max}, got {max_workers_seen})",
                          Fore.YELLOW))
            
        # Proof 3: Workers scaled down
        if final_workers <= initial_workers:
            proofs.append(("✓", "Workers scaled DOWN after queue drain", Fore.GREEN))
        else:
            proofs.append(("⚠", f"Workers still scaling down ({final_workers} remaining)", Fore.YELLOW))
            
        # Proof 4: Queue was processed
        if final_queue == 0:
            proofs.append(("✓", "All jobs processed (queue empty)", Fore.GREEN))
        else:
            proofs.append(("⚠", f"{final_queue} jobs still in queue", Fore.YELLOW))
            
        for symbol, message, color in proofs:
            print(f"  {color}{symbol} {message}{Style.RESET_ALL}")
            
        # Overall verdict
        all_passed = all(p[0] == "✓" for p in proofs)
        
        print(f"\n{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}")
        if all_passed:
            print(f"{Fore.GREEN}{'KEDA IS WORKING! ✓'.center(80)}{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}{'KEDA PARTIALLY WORKING (see details above)'.center(80)}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}\n")
        
        # Save event log
        self.save_event_log()
        
        return all_passed
        
    def save_event_log(self):
        """Save event log to file."""
        log_file = "keda_proof_events.json"
        with open(log_file, 'w') as f:
            json.dump({
                'test_timestamp': datetime.now().isoformat(),
                'events': self.events
            }, f, indent=2)
        print(f"{Fore.CYAN}Event log saved to: {log_file}{Style.RESET_ALL}")


def main():
    parser = argparse.ArgumentParser(
        description="Prove KEDA autoscaling is working",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic proof with 50 jobs
  python prove-keda-works.py --api-url http://localhost:8000
  
  # Stress test with 100 jobs
  python prove-keda-works.py --api-url http://localhost:8000 --num-jobs 100
  
  # Custom KEDA configuration
  python prove-keda-works.py --api-url http://localhost:8000 --target 10 --max-workers 5
        """
    )
    
    parser.add_argument(
        '--api-url',
        required=True,
        help='API service URL (e.g., http://localhost:8000)'
    )
    
    parser.add_argument(
        '--num-jobs',
        type=int,
        default=50,
        help='Number of test jobs to submit (default: 50)'
    )
    
    parser.add_argument(
        '--namespace',
        default='default',
        help='Kubernetes namespace (default: default)'
    )
    
    parser.add_argument(
        '--target',
        type=int,
        default=5,
        help='Target messages per worker (default: 5)'
    )
    
    parser.add_argument(
        '--min-workers',
        type=int,
        default=0,
        help='Minimum worker replicas (default: 0)'
    )
    
    parser.add_argument(
        '--max-workers',
        type=int,
        default=10,
        help='Maximum worker replicas (default: 10)'
    )
    
    args = parser.parse_args()
    
    # Check if kubectl is available
    try:
        subprocess.run(['kubectl', 'version', '--client'], 
                      capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"{Fore.RED}Error: kubectl not found. Please install kubectl and configure access to your cluster.{Style.RESET_ALL}")
        sys.exit(1)
        
    # Check if API is accessible
    try:
        response = requests.get(f"{args.api_url}/health", timeout=5)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"{Fore.RED}Error: Cannot reach API at {args.api_url}/health{Style.RESET_ALL}")
        print(f"{Fore.RED}Error details: {e}{Style.RESET_ALL}")
        print(f"\n{Fore.YELLOW}Tip: Make sure to port-forward the API service:{Style.RESET_ALL}")
        print(f"{Fore.CYAN}  kubectl port-forward svc/video-api 8000:8000{Style.RESET_ALL}")
        sys.exit(1)
        
    # Run the proof
    monitor = KEDAProofMonitor(args.api_url, args.namespace)
    success = monitor.run_proof(
        num_jobs=args.num_jobs,
        target_per_worker=args.target,
        min_replicas=args.min_workers,
        max_replicas=args.max_workers
    )
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
