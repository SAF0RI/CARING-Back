from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..services.composite_service import CompositeService
from ..models import VoiceComposite

router = APIRouter(tags=["composite"])


@router.post("/voices/{voice_id}/composite")
async def recompute_voice_composite(voice_id: int, db: Session = Depends(get_db)):
    service = CompositeService(db)
    try:
        return service.compute_and_save_composite(voice_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"composite compute failed: {str(e)}")


@router.get("/voices/{voice_id}/composite")
async def get_voice_composite(voice_id: int, db: Session = Depends(get_db)):
    row: VoiceComposite = db.query(VoiceComposite).filter(VoiceComposite.voice_id == voice_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    # top_emotion에서 fear -> anxiety 변환
    top_emotion = "anxiety" if row.top_emotion == "fear" else row.top_emotion
    
    return {
        "voice_id": voice_id,
        "valence_x1000": row.valence_x1000,
        "arousal_x1000": row.arousal_x1000,
        "intensity_x1000": row.intensity_x1000,
        "alpha_bps": row.alpha_bps or 0,
        "beta_bps": row.beta_bps or 0,
        "happy_bps": row.happy_bps,
        "sad_bps": row.sad_bps,
        "neutral_bps": row.neutral_bps,
        "angry_bps": row.angry_bps,
        "anxiety_bps": row.fear_bps,  # fear -> anxiety (출력용)
        "surprise_bps": row.surprise_bps,
        "top_emotion": top_emotion,
        "top_emotion_confidence_bps": row.top_emotion_confidence_bps or 0,
    }
