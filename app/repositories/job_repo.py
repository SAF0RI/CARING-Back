from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from ..models import VoiceJobProcess
from ..services.composite_service import CompositeService


def ensure_job_row(session: Session, voice_id: int) -> VoiceJobProcess:
    row = session.query(VoiceJobProcess).filter(VoiceJobProcess.voice_id == voice_id).first()
    if not row:
        row = VoiceJobProcess(voice_id=voice_id, text_done=0, audio_done=0, locked=0)
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def mark_text_done(session: Session, voice_id: int) -> None:
    row = ensure_job_row(session, voice_id)
    row.text_done = 1
    session.commit()


def mark_audio_done(session: Session, voice_id: int) -> None:
    row = ensure_job_row(session, voice_id)
    row.audio_done = 1
    session.commit()


def try_aggregate(session: Session, voice_id: int) -> bool:
    """Try to aggregate when both tasks are done; use a simple DB lock flag to prevent race."""
    try:
        from ..performance_logger import get_performance_logger
        logger = get_performance_logger(voice_id)
        
        row = session.query(VoiceJobProcess).with_for_update().filter(VoiceJobProcess.voice_id == voice_id).first()
        if not row:
            return False
        if row.locked:
            return False
        if not (row.text_done and row.audio_done):
            return False
        # acquire lock
        row.locked = 1
        session.commit()
        
        logger.log_step("voice_composite 입력 시작", category="async")
        # do aggregate
        service = CompositeService(session)
        service.compute_and_save_composite(voice_id)
        logger.log_step("완료", category="async")
        
        # release lock (keep done flags)
        row.locked = 0
        session.commit()
        
        # 로그 파일 저장 및 정리
        logger.save_to_file()
        from ..performance_logger import clear_logger
        clear_logger(voice_id)
        
        return True
    except SQLAlchemyError:
        session.rollback()
        return False
