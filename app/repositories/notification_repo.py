"""Notification Repository"""
from sqlalchemy.orm import Session
from ..models import Notification, Voice, VoiceComposite


def create_notification(session: Session, voice_id: int, name: str, top_emotion: str = None) -> Notification:
    """
    알림 기록 생성
    
    Args:
        session: 데이터베이스 세션
        voice_id: 음성 ID
        name: 연결된 유저의 이름
        top_emotion: top_emotion (voice_composite에서 가져옴, 없으면 None)
        
    Returns:
        Notification: 생성된 알림 기록
    """
    notification = Notification(
        voice_id=voice_id,
        name=name,
        top_emotion=top_emotion
    )
    session.add(notification)
    session.commit()
    session.refresh(notification)
    return notification

