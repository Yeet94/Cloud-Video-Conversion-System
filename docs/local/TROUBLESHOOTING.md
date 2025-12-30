# Docker Compose - Troubleshooting Guide

This guide covers common issues when running the Cloud Video Conversion System with Docker Compose.

## Common Issues

### 1. Services Not Starting

**Symptom:** `docker-compose up` fails or services exit immediately

**Solution:**

```bash
# Check for port conflicts
docker-compose ps

# View detailed logs
docker-compose logs

# Ensure Docker Desktop is running
docker info

# Restart Docker Desktop if needed
```

### 2. Port Already in Use

**Symptom:** Error like `Bind for 0.0.0.0:8000 failed: port is already allocated`

**Solution:**

```bash
# Find process using the port (Windows PowerShell)
netstat -ano | findstr :8000

# Kill the process (replace PID with actual process ID)
taskkill /PID <PID> /F

# Or modify docker-compose.yaml to use different ports
```

### 3. Worker Not Connecting to RabbitMQ

**Symptom:** Worker logs show connection errors to RabbitMQ

**Solution:**

```bash
# Check RabbitMQ is running and healthy
docker-compose ps rabbitmq

# View RabbitMQ logs
docker-compose logs rabbitmq

# Restart RabbitMQ
docker-compose restart rabbitmq

# Check network connectivity
docker-compose exec worker ping rabbitmq
```

### 4. MinIO Upload Failures

**Symptom:** "Upload failed: Network error" in frontend

**Solution:**

```bash
# Check MinIO is running
docker-compose ps minio

# View MinIO logs
docker-compose logs minio

# Verify bucket was created
docker-compose exec minio mc ls /data/

# Manually create bucket if needed
docker-compose exec minio mc mb /data/videos

# Check CORS configuration
# MinIO should allow requests from localhost
```

**Check MinIO environment variables in docker-compose.yaml:**
```yaml
environment:
  MINIO_ROOT_USER: minioadmin
  MINIO_ROOT_PASSWORD: minioadmin
  MINIO_BROWSER_REDIRECT_URL: http://localhost:9001
```

### 5. Database Locked Errors

**Symptom:** SQLite "database is locked" errors in logs

**Solution:**

```bash
# This occurs when multiple instances try to write simultaneously
# For Docker Compose, this is expected with multiple API/worker instances

# Option 1: Reduce worker count temporarily
docker-compose up -d --scale worker=1

# Option 2: Add retry logic (already implemented in code)
# Check shared/database.py for retry configuration

# Option 3: For production, use PostgreSQL instead of SQLite
```

### 6. FFmpeg Conversion Failures

**Symptom:** Jobs stuck in "PROCESSING" or marked as "FAILED"

**Solution:**

```bash
# Check worker logs for FFmpeg errors
docker-compose logs worker | grep -i ffmpeg

# Common causes:
# - Corrupted input video file
# - Unsupported codec
# - Insufficient memory/CPU

# Verify worker has enough resources
docker stats

# Test FFmpeg manually inside worker container
docker-compose exec worker ffmpeg -version
docker-compose exec worker ffmpeg -i /tmp/test.avi /tmp/test.mp4
```

### 7. Grafana Dashboard Not Showing Metrics

**Symptom:** Grafana panels show "No data"

**Solution:**

```bash
# Check Prometheus is scraping targets
# Open http://localhost:9090/targets
# All targets should be "UP"

# Verify API and Worker are exposing metrics
curl http://localhost:8000/metrics
docker-compose exec worker curl http://localhost:8000/metrics

# Check Prometheus configuration
docker-compose exec prometheus cat /etc/prometheus/prometheus.yml

# Restart Prometheus to reload config
docker-compose restart prometheus

# Wait 30 seconds for metrics to be scraped
```

### 8. High Memory Usage

**Symptom:** Docker consuming excessive memory

**Solution:**

```bash
# Check which services are using memory
docker stats

# Limit worker memory in docker-compose.yaml
services:
  worker:
    deploy:
      resources:
        limits:
          memory: 2G

# Reduce number of worker instances
docker-compose up -d --scale worker=1

# Prune unused Docker resources
docker system prune -a
```

### 9. Cannot Access Services from Browser

**Symptom:** "This site can't be reached" errors

**Solution:**

```bash
# Verify services are listening on correct ports
docker-compose ps

# Check if ports are properly mapped
docker-compose port api 8000
docker-compose port frontend 80

# Ensure you're using the correct URL
# Frontend: http://localhost (not http://localhost:80)
# API: http://localhost:8000

# Try accessing from host machine's IP
ipconfig  # Find your IP address
# Then use http://<YOUR_IP>:8000
```

### 10. Old Data Persisting After Restart

**Symptom:** Old jobs/videos remain after `docker-compose down`

**Solution:**

```bash
# To completely reset the system, remove volumes
docker-compose down -v

# This will delete:
# - All job records from SQLite
# - All uploaded/converted videos from MinIO
# - All RabbitMQ messages

# Then start fresh
docker-compose up -d
```

## Useful Debugging Commands

### Check Service Health

```bash
# View all running containers
docker-compose ps

# Check container health
docker inspect <container_name> | grep -A 10 Health

# View resource usage
docker stats
```

### Access Container Shells

```bash
# Access API container
docker-compose exec api /bin/bash

# Access Worker container
docker-compose exec worker /bin/bash

# Access MinIO container
docker-compose exec minio /bin/sh

# Execute Python in API context
docker-compose exec api python
```

### View and Follow Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f worker

# Last 100 lines
docker-compose logs --tail=100 worker

# With timestamps
docker-compose logs -f -t api
```

### Database Inspection

```bash
# Check database file exists
docker-compose exec api ls -lh /data/

# Query job statistics
docker-compose exec api python3 -c "
import sqlite3
conn = sqlite3.connect('/data/jobs.db')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM jobs')
print(f'Total jobs: {cursor.fetchone()[0]}')
cursor.execute('SELECT status, COUNT(*) FROM jobs GROUP BY status')
print('By status:')
for row in cursor.fetchall():
    print(f'  {row[0]}: {row[1]}')
"
```

### Network Debugging

```bash
# Test connectivity between services
docker-compose exec worker ping api
docker-compose exec worker ping minio
docker-compose exec worker ping rabbitmq

# Check DNS resolution
docker-compose exec worker nslookup rabbitmq

# View network configuration
docker network ls
docker network inspect cloud-video-conversion-system_default
```

## Getting Help

If you're still experiencing issues:

1. **Check Logs**: Most issues are revealed in the service logs
   ```bash
   docker-compose logs -f
   ```

2. **Verify Prerequisites**: Ensure Docker Desktop is up-to-date

3. **Clean Slate**: Try a complete reset
   ```bash
   docker-compose down -v
   docker system prune -a
   docker-compose up -d
   ```

4. **Review Architecture**: See [docs/ARCHITECTURE.md](../ARCHITECTURE.md) to understand component interactions

5. **Check GitHub Issues**: Search for similar problems in the repository issues

---

**Need Kubernetes troubleshooting?** See [docs/kubernetes/TROUBLESHOOTING.md](../kubernetes/TROUBLESHOOTING.md)
