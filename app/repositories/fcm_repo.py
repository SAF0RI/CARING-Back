"""FCM 토큰 Repository"""
from typing import List, Optional
from sqlalchemy.orm import Session
from ..models import FcmToken, User


def register_fcm_token(session: Session, user_id: int, fcm_token: str, device_id: Optional[str] = None, platform: Optional[str] = None) -> FcmToken:
    """FCM 토큰 등록 또는 업데이트 (멀티 디바이스 지원)"""
    # 기존 토큰 찾기 (device_id가 있으면 device_id로, 없으면 fcm_token으로)
    existing_token = None
    if device_id:
        existing_token = session.query(FcmToken).filter(
            FcmToken.user_id == user_id,
            FcmToken.device_id == device_id
        ).first()
    else:
        existing_token = session.query(FcmToken).filter(
            FcmToken.user_id == user_id,
            FcmToken.fcm_token == fcm_token
        ).first()
    
    if existing_token:
        # 기존 토큰 업데이트
        existing_token.fcm_token = fcm_token
        existing_token.device_id = device_id or existing_token.device_id
        existing_token.platform = platform or existing_token.platform
        existing_token.is_active = 1  # 활성화
        session.commit()
        session.refresh(existing_token)
        return existing_token
    else:
        # 새 토큰 생성
        new_token = FcmToken(
            user_id=user_id,
            fcm_token=fcm_token,
            device_id=device_id,
            platform=platform,
            is_active=1
        )
        session.add(new_token)
        session.commit()
        session.refresh(new_token)
        return new_token


def deactivate_fcm_tokens_by_user(session: Session, user_id: int) -> int:
    """사용자의 모든 FCM 토큰 비활성화 (로그아웃 시)"""
    count = session.query(FcmToken).filter(
        FcmToken.user_id == user_id,
        FcmToken.is_active == 1
    ).update({"is_active": 0}, synchronize_session=False)
    session.commit()
    return count


def deactivate_fcm_token_by_device(session: Session, user_id: int, device_id: str) -> bool:
    """특정 디바이스의 FCM 토큰 비활성화"""
    token = session.query(FcmToken).filter(
        FcmToken.user_id == user_id,
        FcmToken.device_id == device_id,
        FcmToken.is_active == 1
    ).first()
    
    if token:
        token.is_active = 0
        session.commit()
        return True
    return False


def get_active_fcm_tokens_by_user(session: Session, user_id: int) -> List[FcmToken]:
    """사용자의 모든 활성 FCM 토큰 조회 (멀티 디바이스)"""
    return session.query(FcmToken).filter(
        FcmToken.user_id == user_id,
        FcmToken.is_active == 1
    ).all()


def get_active_fcm_tokens_by_username(session: Session, username: str) -> List[FcmToken]:
    """username으로 활성 FCM 토큰 조회"""
    user = session.query(User).filter(User.username == username).first()
    if not user:
        return []
    return get_active_fcm_tokens_by_user(session, user.user_id)

