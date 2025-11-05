from typing import Dict, Optional
from sqlalchemy.orm import Session
from ..models import VoiceComposite
from ..services.va_fusion import to_bps_from_unit_minus1_1, to_x1000


def upsert_voice_composite(session: Session, voice_id: int, res: Dict[str, object]) -> VoiceComposite:
    """Upsert voice_composite row using computed fusion result dict."""
    row: Optional[VoiceComposite] = session.query(VoiceComposite).filter(VoiceComposite.voice_id == voice_id).first()
    if not row:
        row = VoiceComposite(voice_id=voice_id)
        session.add(row)

    # Scalars (x1000/bps)
    row.text_score_bps = to_bps_from_unit_minus1_1(float(res.get("V_text", 0.0)))
    row.text_magnitude_x1000 = to_x1000(float(res.get("A_text", 0.0)))

    row.alpha_bps = int(round(float(res.get("alpha", 0.0)) * 10000))
    row.beta_bps = int(round(float(res.get("beta", 0.0)) * 10000))

    row.valence_x1000 = to_x1000(float(res.get("V_final", 0.0)))
    row.arousal_x1000 = to_x1000(float(res.get("A_final", 0.0)))
    row.intensity_x1000 = to_x1000(float(res.get("intensity", 0.0)))

    per = res.get("per_emotion_bps", {}) or {}
    row.happy_bps = int(per.get("happy", 0))
    row.sad_bps = int(per.get("sad", 0))
    row.neutral_bps = int(per.get("neutral", 0))
    row.angry_bps = int(per.get("angry", 0))
    row.fear_bps = int(per.get("fear", 0))
    row.surprise_bps = int(per.get("surprise", 0))

    row.top_emotion = str(res.get("top_emotion", "neutral"))
    row.top_emotion_confidence_bps = int(res.get("top_confidence_bps", 0))

    session.commit()
    session.refresh(row)
    return row
