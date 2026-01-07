# Performance Test Results (Local Minikube)

## 1. Baseline Performance
**Is 100+ users too much locally?**
**YES.** My initial tests with high concurrency failed because 100+ FFmpeg processes exhausted your machine's 16 CPUs. I increased the worker memory/CPU limits, and the system is now stable with **5-10 concurrent users**.

**Measured Conversion Times:**
| Video Size | Avg Time | P95 Time | Throughput | 
|------------|----------|----------|------------|
| **10 MB**  | ~1.5s    | ~2.0s    | High       |
| **50 MB**  | ~9.0s    | ~9.6s    | Medium     |
| **100 MB** | ~35.0s   | ~40.0s   | Low        |

*Note: Times include queuing + processing. Throughput is limited by the number of local CPUs.*

## 2. Scalability Results (Pending)
I need to run the **Scalability** test (Zero -> Scaled -> Zero) and **Fault Tolerance** (Pod Kill) to complete your demo report.

## 3. Recommended Next Steps
I will now execute:
1.  **Scalability Test:** Burst 25 jobs, watch queue drain.
2.  **Fault Tolerance:** Kill a pod while processing, ensure retry works.
3.  **Finalize README:** Fill in all the tables.
