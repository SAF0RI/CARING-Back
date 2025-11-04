from typing import Dict, Tuple, Optional
from sqlalchemy.orm import Session
from ..models import VoiceAnalyze, VoiceContent


def get_audio_probs_by_voice_id(session: Session, voice_id: int) -> Dict[str, float]:
    """Read voice_analyze bps and convert to probabilities (sum~=1).
    Returns dict with keys: happy,sad,neutral,angry,fear,surprise
    """
    va: Optional[VoiceAnalyze] = session.query(VoiceAnalyze).filter(VoiceAnalyze.voice_id == voice_id).first()
    if not va:
        return {k: 0.0 for k in ["happy", "sad", "neutral", "angry", "fear", "surprise"]}
    def p(x: Optional[int]) -> float:
        try:
            return max(0.0, float(x or 0) / 10000.0)
        except Exception:
            return 0.0
    probs = {
        "happy": p(va.happy_bps),
        "sad": p(va.sad_bps),
        "neutral": p(va.neutral_bps),
        "angry": p(va.angry_bps),
        "fear": p(va.fear_bps),
        "surprise": p(va.surprise_bps),
    }
    s = sum(probs.values())
    if s > 0:
        for k in probs:
            probs[k] = probs[k] / s
    return probs


def get_text_sentiment_by_voice_id(session: Session, voice_id: int) -> Tuple[float, float]:
    """Read voice_content score/magnitude and convert to unit ranges.
    
    스코어 스케일 복구:
    - 읽을 때: score = (score_bps / 10000) * 2 - 1  # score∈[-1,1]
    - 과거 음수 데이터 보정: score_bps < 0인 경우도 처리
    - magnitude = magnitude_x1000 / 1000.0
    """
    vc: Optional[VoiceContent] = session.query(VoiceContent).filter(VoiceContent.voice_id == voice_id).first()
    if not vc:
        return 0.0, 0.0
    try:
        score_bps = vc.score_bps if vc.score_bps is not None else 5000  # 기본값: 중립 (0)
        
        # 음수인 경우 (과거 데이터): 보정 필요
        if score_bps < 0:
            # 임시 가정: 음수는 10,000 스케일 없이 *10000만 한 값(예: -0.8→-8000)
            # 절대값이 1만 이하인 음수만 보정
            if score_bps >= -10000:
                # 보정: ((score_bps/10000.0)+1.0)*5000
                score_bps = max(0, min(10000, int(round(((float(score_bps) / 10000.0) + 1.0) * 5000))))
            else:
                # 1만 이상 음수는 수동 확인 필요, 기본값 사용
                score_bps = 5000
        
        # 스코어 스케일 복구: score = (score_bps / 10000) * 2 - 1
        score = (float(score_bps) / 10000.0) * 2.0 - 1.0
    except Exception:
        score = 0.0
    
    try:
        magnitude_x1000 = vc.magnitude_x1000 if vc.magnitude_x1000 is not None else 0
        magnitude = float(magnitude_x1000) / 1000.0
    except Exception:
        magnitude = 0.0
    
    # clamp score to [-1, 1]
    score = max(-1.0, min(1.0, score))
    if magnitude < 0:
        magnitude = 0.0
    
    return score, magnitude
