"""메모리 사용량 모니터링 유틸리티"""
import os
import sys
import psutil
from typing import Dict, Any
from datetime import datetime


def get_memory_info() -> Dict[str, Any]:
    """현재 프로세스의 메모리 사용량 정보 반환"""
    try:
        process = psutil.Process(os.getpid())
        
        # 프로세스 메모리 정보
        mem_info = process.memory_info()
        mem_percent = process.memory_percent()
        
        # 시스템 메모리 정보
        system_mem = psutil.virtual_memory()
        
        # 스레드 정보
        num_threads = process.num_threads()
        
        # CPU 사용률
        cpu_percent = process.cpu_percent(interval=0.1)
        
        return {
            "process": {
                "rss_mb": round(mem_info.rss / (1024 * 1024), 2),  # 실제 물리 메모리 사용량
                "vms_mb": round(mem_info.vms / (1024 * 1024), 2),  # 가상 메모리 사용량
                "percent": round(mem_percent, 2),  # 전체 시스템 대비 비율
                "num_threads": num_threads,
                "cpu_percent": round(cpu_percent, 2),
            },
            "system": {
                "total_mb": round(system_mem.total / (1024 * 1024), 2),
                "available_mb": round(system_mem.available / (1024 * 1024), 2),
                "used_mb": round(system_mem.used / (1024 * 1024), 2),
                "percent": round(system_mem.percent, 2),
            },
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "error": f"Failed to get memory info: {str(e)}",
            "timestamp": datetime.now().isoformat(),
        }


def get_memory_usage_mb() -> float:
    """현재 프로세스의 메모리 사용량을 MB로 반환 (간단한 버전)"""
    try:
        process = psutil.Process(os.getpid())
        return round(process.memory_info().rss / (1024 * 1024), 2)
    except Exception:
        return 0.0


def log_memory_info(context: str = ""):
    """메모리 정보를 로그로 출력"""
    info = get_memory_info()
    if "error" in info:
        print(f"[MEMORY] Error: {info['error']}", flush=True)
        return
    
    proc = info["process"]
    sys_mem = info["system"]
    
    context_str = f"[{context}] " if context else ""
    print(
        f"[MEMORY]{context_str} "
        f"Process: {proc['rss_mb']}MB ({proc['percent']:.1f}%), "
        f"System: {sys_mem['used_mb']:.0f}MB/{sys_mem['total_mb']:.0f}MB ({sys_mem['percent']:.1f}%), "
        f"Threads: {proc['num_threads']}, "
        f"CPU: {proc['cpu_percent']:.1f}%",
        flush=True
    )


def check_memory_threshold(threshold_mb: float = 2048.0) -> bool:
    """메모리 사용량이 임계값을 초과하는지 확인"""
    try:
        process = psutil.Process(os.getpid())
        rss_mb = process.memory_info().rss / (1024 * 1024)
        return rss_mb > threshold_mb
    except Exception:
        return False

