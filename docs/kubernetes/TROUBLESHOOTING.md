# Kubernetes - Troubleshooting Guide

This guide covers common issues when deploying the Cloud Video Conversion System on Kubernetes (Minikube or production).

## Common Issues

### 1. Pods Stuck in Pending State

**Symptom:** Pods remain in "Pending" status and never start

**Diagnosis:**

```bash
kubectl get pods -n video-processing
kubectl describe pod <pod-name> -n video-processing
```

**Common Causes:**

**Insufficient Resources:**
```bash
# Check node resources
kubectl describe nodes

# Look for "Insufficient cpu" or "Insufficient memory" messages

# Solution: Restart Minikube with more resources
minikube stop
minikube start --cpus=4 --memory=8192
```

**PVC Not Bound:**
```bash
# Check PVC status
kubectl get pvc -n video-processing

# If PVC is "Pending", check for StorageClass issues
kubectl describe pvc database-pvc -n video-processing

# Solution depends on the error message
```

---

### 2. ImagePullBackOff Errors

**Symptom:** Pods show "ImagePullBackOff" or "ErrImagePull"

**Diagnosis:**

```bash
kubectl describe pod <pod-name> -n video-processing
# Look for "Failed to pull image" messages
```

**Solution for Minikube:**

```bash
# Ensure Docker is using Minikube's registry
& minikube docker-env --shell powershell | Invoke-Expression

# Rebuild images
docker build -t video-api:latest -f api/Dockerfile .
docker build -t video-worker:latest -f worker/Dockerfile .
docker build -t video-frontend:latest -f frontend/Dockerfile .

# Verify images exist in Minikube
docker images | findstr video

# Delete and recreate pods
kubectl rollout restart deployment -n video-processing
```

**Solution for Production:**

```bash
# Ensure images are pushed to your registry
docker tag video-api:latest <your-registry>/video-api:latest
docker push <your-registry>/video-api:latest

# Update deployment manifests to use registry URL
# imagePullPolicy: Always or IfNotPresent
```

---

### 3. KEDA Not Scaling Workers

**Symptom:** Worker pods don't scale despite queue having messages

**Diagnosis:**

```bash
# Check ScaledObject status
kubectl get scaledobject -n video-processing
kubectl describe scaledobject worker-scaledobject -n video-processing

# Check HPA created by KEDA
kubectl get hpa -n video-processing

# View KEDA operator logs
kubectl logs -n keda deployment/keda-operator --tail=100
```

**Common Causes:**

**KEDA Not Installed:**
```bash
# Verify KEDA is running
kubectl get pods -n keda

# If not found, install KEDA
kubectl apply -f https://github.com/kedacore/keda/releases/download/v2.12.0/keda-2.12.0.yaml
```

**RabbitMQ Connection Issues:**
```bash
# Check ScaledObject events
kubectl describe scaledobject worker-scaledobject -n video-processing

# Look for authentication or connection errors

# Verify RabbitMQ credentials in configmap
kubectl get configmap -n video-processing app-config -o yaml
```

**Queue is Empty:**
```bash
# Check actual queue depth in RabbitMQ
kubectl port-forward svc/rabbitmq 15672:15672 -n video-processing
# Visit http://localhost:15672 (guest/guest)
# Navigate to Queues tab
```

---

### 4. Ingress Not Working

**Symptom:** Cannot access services via http://localhost

**Diagnosis:**

```bash
# Check Ingress status
kubectl get ingress -n video-processing
kubectl describe ingress video-ingress -n video-processing

# Check Ingress controller
kubectl get pods -n ingress-nginx
# Or for Minikube addon:
kubectl get pods -n kube-system | grep ingress
```

**Solution for Minikube:**

```bash
# Ensure Ingress addon is enabled
minikube addons enable ingress

# Verify Ingress controller is running
kubectl get pods -n ingress-nginx

# Start Minikube tunnel (REQUIRED)
minikube tunnel
# Keep this running in a separate terminal

# Test connectivity
curl http://localhost/api/health
```

**Check Ingress Configuration:**
```bash
# Verify Ingress rules
kubectl get ingress -n video-processing -o yaml

# Common issues:
# - Wrong service names
# - Wrong ports
# - Missing annotations
```

---

### 5. MinIO Bucket Not Initialized

**Symptom:** Upload fails with "Bucket does not exist"

**Diagnosis:**

```bash
# Check MinIO init job
kubectl get jobs -n video-processing
kubectl logs job/minio-init -n video-processing

# Check MinIO pod logs
kubectl logs -l app=minio -n video-processing
```

**Solution:**

```bash
# Manually create bucket
kubectl exec -it deploy/minio -n video-processing -- sh

# Inside the pod:
mc config host add local http://localhost:9000 minioadmin minioadmin
mc mb local/videos
mc policy set download local/videos
exit

# Or delete and recreate the init job
kubectl delete job minio-init -n video-processing
kubectl apply -f k8s/minio.yaml
```

---

### 6. Metrics Not Showing in Grafana

**Symptom:** Grafana dashboard shows "No data"

**Diagnosis:**

```bash
# Check Prometheus targets
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090
# Visit http://localhost:9090/targets
# All targets should be "UP"
```

**Common Causes:**

**ServiceMonitors Not Created:**
```bash
# Check ServiceMonitors exist
kubectl get servicemonitor -n monitoring

# If not found, apply monitoring manifests
kubectl apply -f k8s/monitoring/
```

**Metrics Not Exposed:**
```bash
# Verify API is exposing metrics
kubectl port-forward svc/api 8000:8000 -n video-processing
curl http://localhost:8000/metrics

# Verify Worker is exposing metrics
kubectl exec -it deployment/worker -n video-processing -- curl localhost:8000/metrics
```

**Prometheus Not Scraping:**
```bash
# Check Prometheus configuration
kubectl get prometheus -n monitoring -o yaml

# Look for serviceMonitorSelector configuration

# Check Prometheus operator logs
kubectl logs -n monitoring -l app.kubernetes.io/name=prometheus-operator
```

---

### 7. Database Locked Errors

**Symptom:** SQLite "database is locked" errors in API/Worker logs

**Diagnosis:**

```bash
kubectl logs -l app=api -n video-processing | grep -i "database"
kubectl logs -l app=worker -n video-processing | grep -i "database"
```

**Solutions:**

**Short Term:**
```bash
# Reduce concurrent access
kubectl scale deployment api --replicas=1 -n video-processing
kubectl scale deployment worker --replicas=1 -n video-processing
```

**Verify PVC Access Mode:**
```bash
kubectl get pvc database-pvc -n video-processing -o yaml
# Should have accessModes: ReadWriteMany
```

**Long Term (Production):**
- Replace SQLite with PostgreSQL or MySQL
- See [PRODUCTION.md](PRODUCTION.md) for migration guide

---

### 8. Worker Pod OOM (Out of Memory) Kills

**Symptom:** Worker pods restart frequently, logs show "OOMKilled"

**Diagnosis:**

```bash
# Check pod status
kubectl get pods -n video-processing

# View pod events
kubectl describe pod <worker-pod-name> -n video-processing
# Look for "Reason: OOMKilled"

# Check resource limits
kubectl get deployment worker -n video-processing -o yaml | grep -A 5 resources
```

**Solution:**

```bash
# Option 1: Increase memory limits in worker-deployment.yaml
# Edit k8s/worker-deployment.yaml:
resources:
  limits:
    memory: 4Gi  # Increase from 2Gi

# Apply changes
kubectl apply -f k8s/worker-deployment.yaml

# Option 2: Process smaller videos
# Or optimize FFmpeg settings to use less memory
```

---

### 9. Jobs Stuck in PROCESSING Status

**Symptom:** Jobs never complete, remain in "PROCESSING"

**Diagnosis:**

```bash
# Check worker logs
kubectl logs -f -l app=worker -n video-processing

# Common errors:
# - FFmpeg failures
# - MinIO connection timeouts
# - Out of memory
```

**Solutions:**

**FFmpeg Failures:**
```bash
# Check for FFmpeg errors in logs
kubectl logs -l app=worker -n video-processing | grep -i ffmpeg

# Test FFmpeg manually
kubectl exec -it deployment/worker -n video-processing -- ffmpeg -version
```

**MinIO Connection Issues:**
```bash
# Test connectivity from worker to MinIO
kubectl exec -it deployment/worker -n video-processing -- ping minio

# Check MinIO is accessible
kubectl get svc minio -n video-processing
```

**Job Timeout:**
```bash
# Check RabbitMQ message visibility timeout
kubectl port-forward svc/rabbitmq 15672:15672 -n video-processing
# Visit http://localhost:15672
# Check queue settings for timeout configuration
```

---

### 10. High CPU Usage / Performance Issues

**Symptom:** Cluster slow, high CPU utilization

**Diagnosis:**

```bash
# Check resource usage
kubectl top nodes
kubectl top pods -n video-processing

# Identify resource-intensive pods
kubectl top pods --all-namespaces --sort-by=cpu
```

**Solutions:**

```bash
# Option 1: Limit worker concurrency
# Edit k8s/worker-deployment.yaml to reduce CPU limits

# Option 2: Increase Minikube resources
minikube stop
minikube start --cpus=6 --memory=10240

# Option 3: Reduce KEDA max replicas
# Edit k8s/keda-scaledobject.yaml:
maxReplicaCount: 5  # Reduce from 10

kubectl apply -f k8s/keda-scaledobject.yaml
```

---

## Useful Debugging Commands

### Pod Management

```bash
# View all pods
kubectl get pods -n video-processing

# Describe pod (detailed status)
kubectl describe pod <pod-name> -n video-processing

# View logs
kubectl logs <pod-name> -n video-processing

# Follow logs in real-time
kubectl logs -f <pod-name> -n video-processing

# Previous container logs (if pod restarted)
kubectl logs <pod-name> -n video-processing --previous

# Execute into pod
kubectl exec -it <pod-name> -n video-processing -- /bin/bash
```

### Deployment Management

```bash
# Restart deployment
kubectl rollout restart deployment <deployment-name> -n video-processing

# Scale deployment
kubectl scale deployment <deployment-name> --replicas=3 -n video-processing

# View deployment status
kubectl rollout status deployment/<deployment-name> -n video-processing

# View deployment history
kubectl rollout history deployment/<deployment-name> -n video-processing
```

### Service & Networking

```bash
# List services
kubectl get svc -n video-processing

# Test service connectivity
kubectl run test-pod --rm -it --image=busybox -n video-processing -- /bin/sh
# Inside pod:
wget -O- http://api:8000/health
ping minio

# Port forward service
kubectl port-forward svc/<service-name> <local-port>:<service-port> -n video-processing
```

### Resource Checking

```bash
# View resource usage
kubectl top nodes
kubectl top pods -n video-processing

# Describe node resources
kubectl describe nodes

# View events
kubectl get events -n video-processing --sort-by='.lastTimestamp'
```

### Configuration & Secrets

```bash
# View ConfigMap
kubectl get configmap -n video-processing
kubectl describe configmap app-config -n video-processing

# Edit ConfigMap
kubectl edit configmap app-config -n video-processing

# View Secrets (base64 encoded)
kubectl get secrets -n video-processing
kubectl get secret <secret-name> -n video-processing -o yaml
```

---

## Getting Help

If you're still experiencing issues:

1. **Check Pod Logs**: Most issues are revealed in pod logs
   ```bash
   kubectl logs -f -l app=worker -n video-processing
   ```

2. **Check Events**: System events often show the root cause
   ```bash
   kubectl get events -n video-processing --sort-by='.lastTimestamp'
   ```

3. **Clean Slate**: Try redeploying
   ```bash
   kubectl delete namespace video-processing
   kubectl apply -f k8s/
   ```

4. **Minikube Reset**: For Minikube, start fresh
   ```bash
   minikube delete
   # Then redeploy from scratch
   ```

5. **Review Architecture**: See [docs/ARCHITECTURE.md](../ARCHITECTURE.md)

6. **Check GitHub Issues**: Search the repository for similar problems

---

**Need Docker Compose troubleshooting?** See [docs/local/TROUBLESHOOTING.md](../local/TROUBLESHOOTING.md)
