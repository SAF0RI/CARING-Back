from typing import Dict
from sqlalchemy.orm import Session
from ..repositories.voice_repo import get_audio_probs_by_voice_id, get_text_sentiment_by_voice_id
from ..services.va_fusion import fuse_VA, to_x1000
from ..repositories.composite_repo import upsert_voice_composite


class CompositeService:
    def __init__(self, db: Session):
        self.db = db

    def compute_and_save_composite(self, voice_id: int) -> Dict[str, int]:
        """Compute VA fusion from existing voice_analyze and voice_content, upsert, and return scaled dict."""
        audio_probs = get_audio_probs_by_voice_id(self.db, voice_id)
        text_score, text_mag = get_text_sentiment_by_voice_id(self.db, voice_id)
        res = fuse_VA(audio_probs, text_score, text_mag)
        row = upsert_voice_composite(self.db, voice_id, res)
        return {
            "voice_id": voice_id,
            "updated": True,
            "valence_x1000": row.valence_x1000,
            "arousal_x1000": row.arousal_x1000,
            "intensity_x1000": row.intensity_x1000,
            "alpha_bps": row.alpha_bps or 0,
            "beta_bps": row.beta_bps or 0,
            "happy_bps": row.happy_bps,
            "sad_bps": row.sad_bps,
            "neutral_bps": row.neutral_bps,
            "angry_bps": row.angry_bps,
            "fear_bps": row.fear_bps,
            "surprise_bps": row.surprise_bps,
            "top_emotion": row.top_emotion,
            "top_emotion_confidence_bps": row.top_emotion_confidence_bps or 0,
        }
