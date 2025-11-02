"""음성 업로드 성능 추적 유틸리티"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

PERFORMANCE_LOG_DIR = Path("performance_logs")
PERFORMANCE_LOG_DIR.mkdir(exist_ok=True)


class PerformanceLogger:
    """음성 업로드 성능 추적 로거"""
    
    def __init__(self, voice_id: Optional[int] = None):
        self.voice_id = voice_id
        self.start_time = time.time()
        self.steps: Dict[str, float] = {}
        self.step_order = []
        self.step_category: Dict[str, str] = {}  # "serial" or "async"
        
    def log_step(self, step_name: str, category: str = "serial"):
        """단계 로그 기록
        
        Args:
            step_name: 단계 이름
            category: "serial" (순차 작업) or "async" (비동기 작업)
        """
        elapsed = time.time() - self.start_time
        self.steps[step_name] = elapsed
        if step_name not in self.step_order:
            self.step_order.append(step_name)
        self.step_category[step_name] = category
        
        # 콘솔에도 출력
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(f"[PERF][{timestamp}][{category.upper()}] {step_name}: {elapsed:.3f}s", flush=True)
    
    def add_step_with_time(self, step_name: str, elapsed_time: float, category: str = "serial"):
        """기존 단계 추가 (시간 정보 포함)"""
        self.steps[step_name] = elapsed_time
        if step_name not in self.step_order:
            self.step_order.append(step_name)
        self.step_category[step_name] = category
    
    def get_summary(self) -> Dict:
        """성능 요약 반환"""
        total = time.time() - self.start_time
        
        # Serial 작업과 Async 작업 분리
        serial_steps = []
        async_steps = []
        prev_serial_time = 0.0
        prev_async_time = 0.0
        
        for step in self.step_order:
            step_time = self.steps[step]
            category = self.step_category.get(step, "serial")
            
            if category == "async":
                step_duration = step_time - prev_async_time if prev_async_time > 0 else step_time
                async_steps.append({
                    "step": step,
                    "elapsed_from_start": round(step_time, 3),
                    "duration": round(step_duration, 3)
                })
                prev_async_time = step_time
            else:
                step_duration = step_time - prev_serial_time
                serial_steps.append({
                    "step": step,
                    "elapsed_from_start": round(step_time, 3),
                    "duration": round(step_duration, 3)
                })
                prev_serial_time = step_time
        
        return {
            "voice_id": self.voice_id,
            "total_duration": round(total, 3),
            "serial_work": {
                "steps": serial_steps,
                "total": round(serial_steps[-1]["elapsed_from_start"] if serial_steps else 0, 3)
            },
            "async_work": {
                "steps": async_steps,
                "total": round(async_steps[-1]["elapsed_from_start"] if async_steps else 0, 3)
            },
            "timestamp": datetime.now().isoformat()
        }
    
    def save_to_file(self):
        """로그 파일에 저장"""
        if not self.voice_id:
            self.voice_id = int(time.time() * 1000)  # fallback to timestamp
        
        log_file = PERFORMANCE_LOG_DIR / f"voice_{self.voice_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        summary = self.get_summary()
        
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        print(f"[PERF] 로그 저장 완료: {log_file}", flush=True)


# 전역 인스턴스 관리 (voice_id별로 관리)
_loggers: Dict[int, PerformanceLogger] = {}


def get_performance_logger(voice_id: int, preserve_time: Optional[float] = None) -> PerformanceLogger:
    """voice_id별 성능 로거 가져오기 또는 생성"""
    if voice_id not in _loggers:
        _loggers[voice_id] = PerformanceLogger(voice_id=voice_id)
        if preserve_time is not None:
            _loggers[voice_id].start_time = preserve_time
    return _loggers[voice_id]


def clear_logger(voice_id: int):
    """로거 정리 (메모리 관리)"""
    if voice_id in _loggers:
        del _loggers[voice_id]

