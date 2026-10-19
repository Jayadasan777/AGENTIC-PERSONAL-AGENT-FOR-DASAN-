#!/usr/bin/env python3
"""AURA Phase 6 CLI: Benchmark host hardware and recommend open-weight LLMs."""

from __future__ import annotations

import json
import sys

from backend.app.deployment.benchmarking import (
    detect_hardware_specs,
    generate_benchmark_report,
)


def main() -> None:
    print("=" * 70)
    print("  AURA AGENTIC SYSTEM: HOST HARDWARE & MODEL BENCHMARKING")
    print("=" * 70)

    specs = detect_hardware_specs()
    print(f"OS:                 {specs.os_name} ({specs.architecture})")
    print(f"CPU Cores/Threads:  {specs.cpu_cores} physical / {specs.cpu_threads} logical")
    print(
        f"System RAM:         {specs.ram_available_gb:.1f} GB available / {specs.ram_total_gb:.1f} GB total"
    )
    if specs.gpu_available:
        print(f"GPU:                {specs.gpu_name}")
        print(
            f"VRAM:               {specs.vram_available_gb:.1f} GB available / {specs.vram_total_gb:.1f} GB total"
        )
    else:
        print("GPU:                None detected (CPU execution mode)")
    print(f"Free Disk Space:    {specs.disk_free_gb:.1f} GB")
    print("-" * 70)

    report = generate_benchmark_report(specs, target_context=8192)
    top_pick = report.get("primary_recommendation")

    if top_pick:
        print("RECOMMENDED OPEN-WEIGHT MODEL FOR THIS HOST:")
        print(f"  Model:            {top_pick['model_name']}")
        print(f"  Quantization:     {top_pick['quantization']}")
        print(
            f"  Memory Footprint: {top_pick['total_required_ram_gb']:.2f} GB (Weights: {top_pick['weights_ram_gb']} GB, KV: {top_pick['kv_cache_ram_gb']} GB)"
        )
        print(f"  Offload Layers:   {top_pick['recommended_gpu_layers']} GPU layers")
        print(f"  Estimated Speed:  {top_pick['estimated_speed_category']}")
        print(f"  Operational Note: {top_pick['notes']}")
    else:
        print("WARNING: Host resources are constrained. Cloud model provider is recommended.")

    print("=" * 70)

    if "--json" in sys.argv:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
