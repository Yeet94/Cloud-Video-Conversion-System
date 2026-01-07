# Adding Smart Load Balancing Metrics to Grafana

## 🎯 New Metrics for Your Demo

I've created 7 new panels to showcase the smart load balancing features:

### **Panels Added:**

1. **🔥 Worker CPU Usage (Per Pod)** (Time series)
   - Shows CPU % for each worker individually
   - Yellow threshold at 70% (HPA trigger)
   - Red threshold at 85% (readiness probe limit)
   
2. **⚖️ Dual Autoscaling - HPA vs KEDA** (Time series)
   - Blue line: HPA desired replicas (CPU/Memory based)
   - Green line: Current replicas
   - Orange line: Actual worker pods
   - **Shows which autoscaler is winning!**

3. **💚 Worker Readiness Status** (Time series/Bars)
   - 1 = Ready ✅ (green)
   - 0 = Not Ready ❌ (red)
   - **See smart isolation in action!**

4. **🧠 Worker Memory Usage (Per Pod)** (Time series)
   - Memory consumption per worker
   - Thresholds at 1GB and 1.6GB

5. **📊 HPA Metrics** (Stat)
   - CPU Target: 70%
   - Memory Target: 80%

6. **🎯 Average Worker CPU** (Stat with color)
   - Green (<50%), Yellow (50-70%), Orange (70-85%), Red (>85%)
   - **Changes color in real-time during demos!**

7. **✅ Ready Workers Count** (Stat)
   - Shows Ready/Total ratio
   - Red if 0 workers, Green if 2+

---

## 📥 **How to Import to Grafana**

### **Option 1: Manual Panel Addition** (Recommended for Demo)

1. **Access Grafana:**
   ```powershell
   kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80
   ```
   Open: http://localhost:3000 (admin / admin)

2. **Open Your Dashboard:**
   - Navigate to Dashboards → Browse
   - Find "Video Processing System"

3. **Add New Panels:**
   - Click "Add" → "Visualization"
   - Copy queries from `smart-load-balancing-panels.json` one by one

### **Option 2: Use the Panel JSON Directly**

1. In Grafana, click the dashboard settings (gear icon)
2. Go to "JSON Model"
3. Find the `"panels": [` array
4. Insert the panels from `smart-load-balancing-panels.json` into the array
5. Click "Save JSON"

---

## 🔍 **Key Queries for Your Demo**

### **1. Worker CPU Per Pod:**
```promql
sum(rate(container_cpu_usage_seconds_total{namespace="video-processing", pod=~"worker-.*"}[1m])) by (pod) * 100
```

### **2. HPA Desired Replicas:**
```promql
kube_horizontalpodautoscaler_status_desired_replicas{namespace="video-processing", horizontalpodautoscaler="worker-cpu-hpa"}
```

### **3. Worker Readiness:**
```promql
kube_pod_status_ready{namespace="video-processing", pod=~"worker-.*", condition="true"}
```

### **4. Average Worker CPU (Great for stat panel):**
```promql
avg(sum(rate(container_cpu_usage_seconds_total{namespace="video-processing", pod=~"worker-.*"}[1m])) by (pod) * 100)
```

---

## 🎬 **Demo Flow with These Metrics**

### **Step 1: Show Baseline**
- Point to "Average Worker CPU" → Should be low (~10-20%)
- Point to "Ready Workers Count" → Should match total workers
- Point to "Worker CPU Usage" → All workers low and similar

### **Step 2: Start CPU Autoscaling Test**
```powershell
python scripts/smart-load-balancing-test.py cpu-scaling
```

**What to show in Grafana:**
1. **Worker CPU Usage** panel → Watch one worker spike to 80%+
2. **Dual Autoscaling** panel → HPA Desired line goes up (1 → 3)
3. **Active Workers** stat → Count increases
4. **Average Worker CPU** stat → Color changes yellow → orange

### **Step 3: Show Readiness Isolation** (If time)
```powershell
python scripts/smart-load-balancing-test.py readiness
```

**What to show:**
1. **Worker Readiness Status** → One bar drops from 1 to 0  
2. **Ready Workers Count** → Goes from "3/3" to "2/3"
3. New jobs won't route to the unready worker!

---

## 💡 **Quick Grafana Tips**

### **Make Metrics More Dramatic:**
- Set refresh rate to 5 seconds (top right)
- Use "Last 5 minutes" time range during demos
- Enable auto-refresh

###  **Color Thresholds:**
The panels are configured with:
- 🟢 Green: 0-50% CPU (healthy)
- 🟡 Yellow: 50-70% CPU (moderate)
- 🟠 Orange: 70-85% CPU (HPA will scale!)
- 🔴 Red: 85%+ CPU (readiness probe fails!)

---

## ✅ **Verification**

After adding panels, you should see:
- 7 new panels in your dashboard
- Real-time CPU metrics updating
- HPA autoscaling visualization
- Readiness status tracking

**All panels use Prometheus as datasource** - if metrics don't show:
1. Verify ServiceMonitors are deployed: `kubectl get servicemonitor -n monitoring`
2. Check Prometheus is scraping: Navigate to http://localhost:9090 and query `up{job="worker"}`

---

**Created:** 2026-01-07  
**File Location:** `monitoring/grafana/dashboards/smart-load-balancing-panels.json`
