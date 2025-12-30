# Deploy Locust to Kubernetes
# This deploys a distributed Locust setup with 1 master and 2 workers

Write-Host "Building Locust Docker image..." -ForegroundColor Cyan
docker build -t locust-load:latest -f tests/load/Dockerfile .

Write-Host "`nLoading image into Minikube..." -ForegroundColor Cyan
minikube image load locust-load:latest

Write-Host "`nDeploying Locust to Kubernetes..." -ForegroundColor Cyan
kubectl apply -f k8s/locust-deployment.yaml

Write-Host "`nWaiting for Locust pods to be ready..." -ForegroundColor Cyan
kubectl wait --for=condition=ready pod -l app=locust -n video-processing --timeout=60s

Write-Host "`n" -NoNewline
Write-Host "========================================" -ForegroundColor Green
Write-Host "Locust Deployed Successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

Write-Host "`nAccess Locust Web UI:" -ForegroundColor Yellow
Write-Host "  Via Port Forward: kubectl port-forward -n video-processing svc/locust-master 8089:8089" -ForegroundColor White
Write-Host "  Then open: http://localhost:8089" -ForegroundColor White

Write-Host "`nPod Status:" -ForegroundColor Yellow
kubectl get pods -n video-processing -l app=locust

Write-Host "`nService Status:" -ForegroundColor Yellow
kubectl get svc -n video-processing -l app=locust
