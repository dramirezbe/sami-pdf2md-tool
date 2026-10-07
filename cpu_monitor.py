#!/usr/bin/env python3
"""Sample per-core CPU usage every second and report stats at the end."""
import psutil
import time
import signal

samples = []
running = True

def stop(sig, frame):
    global running
    running = False

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

print(f"Monitoring {psutil.cpu_count(logical=True)} logical / "
      f"{psutil.cpu_count(logical=False)} physical cores (sampling every 1s)")
print(f"{'Time':>6}  {'Avg%':>5}  {'Max%':>5}  {'Min%':>5}  Per-core")
print("-" * 80)

psutil.cpu_percent(percpu=True)
time.sleep(0.5)

start = time.monotonic()
while running:
    per_core = psutil.cpu_percent(interval=1.0, percpu=True)
    avg = sum(per_core) / len(per_core)
    samples.append({"time": time.monotonic() - start, "avg": avg,
                    "per_core": per_core, "max": max(per_core), "min": min(per_core)})
    elapsed = samples[-1]["time"]
    bars = " ".join(f"{c:5.1f}" for c in per_core)
    print(f"{elapsed:5.0f}s  {avg:5.1f}  {max(per_core):5.1f}  {min(per_core):5.1f}  [{bars}]")

if samples:
    total_avg = sum(s["avg"] for s in samples) / len(samples)
    peak = max(s["avg"] for s in samples)
    low = min(s["avg"] for s in samples)
    idle_samples = sum(1 for s in samples if s["avg"] < 10)
    n_cores = len(samples[0]["per_core"])
    core_avgs = []
    for c in range(n_cores):
        core_avgs.append(sum(s["per_core"][c] for s in samples) / len(samples))
    print(f"\n{'=' * 60}")
    print(f"  Samples: {len(samples)} ({samples[-1]['time']:.0f}s)")
    print(f"  Avg CPU across all cores: {total_avg:.1f}%")
    print(f"  Peak avg: {peak:.1f}%   Low avg: {low:.1f}%")
    print(f"  Idle samples (<10%): {idle_samples} ({100*idle_samples/len(samples):.0f}%)")
    print(f"  Per-core avg: {' '.join(f'{a:.0f}%' for a in core_avgs)}")
    print(f"{'=' * 60}")
