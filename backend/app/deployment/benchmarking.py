"""Host Hardware Specification and Open-Weight Model Benchmark Utility.

Analyzes available CPU, RAM, and GPU/VRAM to provide deterministic
recommendations for deploying open-weight local LLMs in AURA.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger("aura.deployment.benchmarking")


@dataclass(frozen=True)
class HardwareSpecs:
    """Hardware capacity of the current host machine."""

    os_name: str
    architecture: str
    cpu_cores: int
    cpu_threads: int
    ram_total_gb: float
    ram_available_gb: float
    gpu_available: bool
    gpu_name: str | None
    vram_total_gb: float
    vram_available_gb: float
    disk_free_gb: float


@dataclass(frozen=True)
class ModelFitRecommendation:
    """Assessment of whether a specific model can run smoothly on this host."""

    model_name: str
    parameter_count_b: float
    quantization: str
    weights_ram_gb: float
    kv_cache_ram_gb: float
    total_required_ram_gb: float
    fits_in_vram: bool
    fits_in_ram: bool
    recommended: bool
    recommended_gpu_layers: int
    max_context_tokens: int
    estimated_speed_category: str  # "FAST (>30 t/s)", "MODERATE (10-30 t/s)", "SLOW (<10 t/s)"
    notes: str


# Catalog of prominent open-weight models suitable for agentic workloads
MODEL_CATALOG: list[dict[str, Any]] = [
    {
        "name": "Qwen/Qwen2.5-7B-Instruct",
        "params_b": 7.6,
        "default_ctx": 32768,
        "quant_factors": {
            "FP16": 2.0,
            "Q8_0": 1.05,
            "Q5_K_M": 0.72,
            "Q4_K_M": 0.58,
        },
    },
    {
        "name": "meta-llama/Llama-3.1-8B-Instruct",
        "params_b": 8.0,
        "default_ctx": 16384,
        "quant_factors": {
            "FP16": 2.0,
            "Q8_0": 1.05,
            "Q5_K_M": 0.72,
            "Q4_K_M": 0.58,
        },
    },
    {
        "name": "deepseek-ai/DeepSeek-R1-Distill-Qwen-8B",
        "params_b": 8.0,
        "default_ctx": 16384,
        "quant_factors": {
            "FP16": 2.0,
            "Q8_0": 1.05,
            "Q5_K_M": 0.72,
            "Q4_K_M": 0.58,
        },
    },
    {
        "name": "Qwen/Qwen2.5-14B-Instruct",
        "params_b": 14.7,
        "default_ctx": 16384,
        "quant_factors": {
            "FP16": 2.0,
            "Q8_0": 1.05,
            "Q5_K_M": 0.72,
            "Q4_K_M": 0.58,
        },
    },
    {
        "name": "microsoft/phi-4",
        "params_b": 14.0,
        "default_ctx": 16384,
        "quant_factors": {
            "FP16": 2.0,
            "Q8_0": 1.05,
            "Q5_K_M": 0.72,
            "Q4_K_M": 0.58,
        },
    },
    {
        "name": "Qwen/Qwen2.5-32B-Instruct",
        "params_b": 32.5,
        "default_ctx": 8192,
        "quant_factors": {
            "FP16": 2.0,
            "Q8_0": 1.05,
            "Q5_K_M": 0.72,
            "Q4_K_M": 0.58,
        },
    },
]


def detect_hardware_specs() -> HardwareSpecs:
    """Inspect current operating system and hardware devices."""
    os_name = f"{platform.system()} {platform.release()}"
    arch = platform.machine()
    cpu_threads = os.cpu_count() or 4
    cpu_cores = max(1, cpu_threads // 2)

    # RAM detection (safe fallback across OSes)
    ram_total_gb = 16.0
    ram_available_gb = 12.0
    try:
        if platform.system() == "Linux":
            with open("/proc/meminfo") as f:
                meminfo = f.read()
            for line in meminfo.splitlines():
                if line.startswith("MemTotal:"):
                    ram_total_gb = round(int(line.split()[1]) / (1024 * 1024), 2)
                elif line.startswith("MemAvailable:"):
                    ram_available_gb = round(int(line.split()[1]) / (1024 * 1024), 2)
        elif platform.system() == "Windows":
            # Using ctypes or systeminfo fallback
            try:
                import ctypes

                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]

                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(stat)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))  # type: ignore[attr-defined]
                ram_total_gb = round(stat.ullTotalPhys / (1024**3), 2)
                ram_available_gb = round(stat.ullAvailPhys / (1024**3), 2)
            except Exception as e:
                logger.debug("Windows memory check failed: %s", e)
    except Exception as e:
        logger.debug("Failed reading system memory: %s", e)

    # GPU / VRAM detection via nvidia-smi
    gpu_available = False
    gpu_name = None
    vram_total_gb = 0.0
    vram_available_gb = 0.0

    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            out = subprocess.check_output(  # noqa: S603
                [
                    nvidia_smi,
                    "--query-gpu=name,memory.total,memory.free",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                timeout=5,
            ).strip()
            if out:
                first_line = out.splitlines()[0]
                parts = [p.strip() for p in first_line.split(",")]
                if len(parts) >= 3:
                    gpu_name = parts[0]
                    vram_total_gb = round(float(parts[1]) / 1024.0, 2)
                    vram_available_gb = round(float(parts[2]) / 1024.0, 2)
                    gpu_available = True
        except Exception as e:
            logger.debug("nvidia-smi detection failed: %s", e)

    # Free disk space on current partition
    disk_free_gb = 50.0
    try:
        usage = shutil.disk_usage(".")
        disk_free_gb = round(usage.free / (1024**3), 2)
    except Exception as e:
        logger.debug("Disk usage check failed: %s", e)

    return HardwareSpecs(
        os_name=os_name,
        architecture=arch,
        cpu_cores=cpu_cores,
        cpu_threads=cpu_threads,
        ram_total_gb=ram_total_gb,
        ram_available_gb=ram_available_gb,
        gpu_available=gpu_available,
        gpu_name=gpu_name,
        vram_total_gb=vram_total_gb,
        vram_available_gb=vram_available_gb,
        disk_free_gb=disk_free_gb,
    )


def compute_kv_cache_ram(context_tokens: int, params_b: float) -> float:
    """Estimate KV cache memory requirement in GB for a given context length.

    For modern GQA models (e.g. Llama 3, Qwen 2.5): ~0.10-0.12 GB per 1K context for an 8B model.
    """
    gb_per_1k_tokens = (params_b / 8.0) * 0.10
    return round((context_tokens / 1000.0) * gb_per_1k_tokens, 2)


def evaluate_model_fit(
    model: dict[str, Any],
    quant: str,
    specs: HardwareSpecs,
    target_context: int = 8192,
) -> ModelFitRecommendation:
    """Evaluate suitability of a specific model & quantization on host hardware."""
    params_b = float(model["params_b"])
    factor = model["quant_factors"].get(quant, 0.58)

    # Weights memory (bytes = params * factor, plus 10% runtime overhead)
    weights_ram = round(params_b * factor * 1.10, 2)
    kv_cache_ram = compute_kv_cache_ram(target_context, params_b)
    total_req_ram = round(weights_ram + kv_cache_ram, 2)

    # Check VRAM and System RAM fit
    # Leave 1.5 GB safety buffer for OS/display in VRAM, 3 GB in RAM
    effective_vram = max(0.0, specs.vram_available_gb - 1.5)
    effective_ram = max(0.0, specs.ram_available_gb - 3.0)

    fits_in_vram = specs.gpu_available and (total_req_ram <= effective_vram)
    fits_in_ram = total_req_ram <= (effective_ram + effective_vram)

    # Estimate GPU layers offload (assume typical 32-40 layers for 7-14B models)
    total_layers = 32 if params_b <= 8.0 else (48 if params_b <= 14.7 else 64)
    if fits_in_vram:
        gpu_layers = total_layers
        speed = "FAST (>30 t/s)"
        notes = "Full GPU acceleration: model weights and KV cache reside entirely in VRAM."
    elif specs.gpu_available and effective_vram > 2.0:
        # Partial GPU offloading
        fraction = effective_vram / total_req_ram
        gpu_layers = int(total_layers * min(0.9, fraction))
        speed = "MODERATE (10-30 t/s)"
        notes = (
            f"Partial GPU offload ({gpu_layers}/{total_layers} layers in VRAM, rest in system RAM)."
        )
    elif fits_in_ram:
        gpu_layers = 0
        speed = "MODERATE (10-30 t/s)" if specs.cpu_threads >= 8 else "SLOW (<10 t/s)"
        notes = "CPU-only execution with AVX2/AVX512. Fits in available RAM."
    else:
        gpu_layers = 0
        speed = "UNSUITABLE"
        notes = "Insufficient memory: exceeding available RAM and VRAM."

    recommended = fits_in_ram and (speed != "UNSUITABLE")

    return ModelFitRecommendation(
        model_name=model["name"],
        parameter_count_b=params_b,
        quantization=quant,
        weights_ram_gb=weights_ram,
        kv_cache_ram_gb=kv_cache_ram,
        total_required_ram_gb=total_req_ram,
        fits_in_vram=fits_in_vram,
        fits_in_ram=fits_in_ram,
        recommended=recommended,
        recommended_gpu_layers=gpu_layers,
        max_context_tokens=target_context,
        estimated_speed_category=speed,
        notes=notes,
    )


def generate_benchmark_report(
    specs: HardwareSpecs | None = None,
    target_context: int = 8192,
) -> dict[str, Any]:
    """Generate a comprehensive benchmark analysis and deployment recommendation."""
    if specs is None:
        specs = detect_hardware_specs()

    recommendations: list[dict[str, Any]] = []
    recommended_candidates: list[dict[str, Any]] = []

    for model in MODEL_CATALOG:
        for quant in ["Q4_K_M", "Q5_K_M", "Q8_0", "FP16"]:
            rec = evaluate_model_fit(model, quant, specs, target_context=target_context)
            rec_dict = asdict(rec)
            recommendations.append(rec_dict)
            if rec.recommended and quant in ("Q4_K_M", "Q5_K_M"):
                recommended_candidates.append(rec_dict)

    # Pick the top recommended model (prefer fastest suitable 7-8B model)
    best_pick = None
    if recommended_candidates:
        # Prioritize fits_in_vram first, then 8B models, then Q5_K_M over Q4_K_M
        sorted_candidates = sorted(
            recommended_candidates,
            key=lambda r: (
                1 if r["fits_in_vram"] else 0,
                1 if r["quantization"] == "Q5_K_M" else 0,
                -abs(r["parameter_count_b"] - 8.0),
            ),
            reverse=True,
        )
        best_pick = sorted_candidates[0]

    return {
        "hardware": asdict(specs),
        "target_context_tokens": target_context,
        "primary_recommendation": best_pick,
        "all_evaluations": recommendations,
    }
