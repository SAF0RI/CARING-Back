from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from ..models import VoiceJobProcess, Voice, User
from ..services.composite_service import CompositeService


def _send_composite_completion_notification(session: Session, voice_id: int):
    """voice_composite 생성 완료 시 연결된 CARE 사용자에게 알림 발송"""
    # 1. voice 조회
    voice = session.query(Voice).filter(Voice.voice_id == voice_id).first()
    if not voice:
        return
    
    # 2. USER 조회
    user = session.query(User).filter(User.user_id == voice.user_id).first()
    if not user or user.role != 'USER':
        return  # USER만 처리
    
    # 3. 연결된 CARE 사용자 찾기 (connecting_user_code = user.username인 CARE)
    care_user = session.query(User).filter(
        User.role == 'CARE',
        User.connecting_user_code == user.username
    ).first()
    
    if not care_user:
        return  # 연결된 CARE 사용자가 없으면 알림 발송 안 함
    
    # 4. FCM 알림 발송
    try:
        from ..services.fcm_service import FcmService
        fcm_service = FcmService(session)
        
        # 알림 제목 및 내용
        title = "음성 분석 완료"
        body = f"{user.name}님의 음성 분석이 완료되었습니다."
        
        # 알림 데이터 (앱에서 음성 상세 페이지로 이동할 수 있도록)
        data = {
            "type": "voice_composite_completed",
            "voice_id": str(voice_id),
            "user_name": user.name,
            "username": user.username
        }
        
        # CARE 사용자에게 알림 발송
        result = fcm_service.send_notification_to_user(
            user_id=care_user.user_id,
            title=title,
            body=body,
            data=data
        )
        
        import logging
        logging.info(f"FCM notification sent to CARE user (user_id={care_user.user_id}, username={care_user.username}): {result}")
    
    except Exception as e:
        # FCM 서비스 초기화 실패 등은 무시 (로그만 남김)
        import logging
        logging.warning(f"FCM notification skipped (service not available): {str(e)}")


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
        
        # voice_composite 생성 완료 → 연결된 CARE 사용자에게 알림 발송
        try:
            _send_composite_completion_notification(session, voice_id)
        except Exception as e:
            # 알림 실패는 로그만 남기고 전체 프로세스는 계속 진행
            import logging
            logging.error(f"Failed to send FCM notification for voice_id={voice_id}: {str(e)}")
        
        # 로그 파일 저장 및 정리
        logger.save_to_file()
        from ..performance_logger import clear_logger
        clear_logger(voice_id)
        
        return True
    except SQLAlchemyError:
        session.rollback()
        return False
