"""FCM 알림 전송 서비스"""
import os
import json
from typing import List, Dict, Optional
from firebase_admin import credentials, messaging, initialize_app
from sqlalchemy.orm import Session
from ..repositories.fcm_repo import get_active_fcm_tokens_by_user, get_active_fcm_tokens_by_username


# Firebase Admin SDK 초기화 (싱글톤 패턴)
_firebase_app = None


def _get_firebase_app():
    """Firebase Admin SDK 앱 인스턴스 가져오기 (초기화는 최초 1회만)"""
    global _firebase_app
    if _firebase_app is None:
        # 환경 변수에서 Firebase 인증 정보 가져오기
        firebase_cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
        if firebase_cred_json:
            # JSON 문자열로 제공되는 경우
            cred_dict = json.loads(firebase_cred_json)
            cred = credentials.Certificate(cred_dict)
        else:
            # 또는 파일 경로로 제공되는 경우
            cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
            if cred_path and os.path.exists(cred_path):
                cred = credentials.Certificate(cred_path)
            else:
                raise ValueError(
                    "Firebase credentials not found. "
                    "Set FIREBASE_CREDENTIALS_JSON or FIREBASE_CREDENTIALS_PATH environment variable."
                )
        
        _firebase_app = initialize_app(cred)
    
    return _firebase_app


class FcmService:
    """FCM 알림 전송 서비스"""
    
    def __init__(self, db: Session):
        self.db = db
        self.app = _get_firebase_app()
    
    def send_notification_to_user(
        self,
        user_id: int,
        title: str,
        body: str,
        data: Optional[Dict[str, str]] = None
    ) -> Dict[str, int]:
        """
        특정 사용자에게 알림 전송 (멀티 디바이스 지원)
        
        Returns:
            {
                "success_count": 성공한 기기 수,
                "failure_count": 실패한 기기 수,
                "total_count": 전체 기기 수
            }
        """
        tokens = get_active_fcm_tokens_by_user(self.db, user_id)
        
        if not tokens:
            return {
                "success_count": 0,
                "failure_count": 0,
                "total_count": 0,
                "message": "No active FCM tokens found for user"
            }
        
        fcm_tokens = [token.fcm_token for token in tokens]
        return self._send_multicast(fcm_tokens, title, body, data)
    
    def send_notification_to_username(
        self,
        username: str,
        title: str,
        body: str,
        data: Optional[Dict[str, str]] = None
    ) -> Dict[str, int]:
        """username으로 알림 전송"""
        tokens = get_active_fcm_tokens_by_username(self.db, username)
        
        if not tokens:
            return {
                "success_count": 0,
                "failure_count": 0,
                "total_count": 0,
                "message": "No active FCM tokens found for username"
            }
        
        fcm_tokens = [token.fcm_token for token in tokens]
        return self._send_multicast(fcm_tokens, title, body, data)
    
    def _send_multicast(
        self,
        fcm_tokens: List[str],
        title: str,
        body: str,
        data: Optional[Dict[str, str]] = None
    ) -> Dict[str, int]:
        """멀티캐스트 알림 전송"""
        if not fcm_tokens:
            return {
                "success_count": 0,
                "failure_count": 0,
                "total_count": 0
            }
        
        # Android와 iOS 모두 지원하는 메시지 생성
        message = messaging.MulticastMessage(
            tokens=fcm_tokens,
            notification=messaging.Notification(
                title=title,
                body=body
            ),
            data=data or {},
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    sound="default",
                    channel_id="default"
                )
            ),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        sound="default",
                        badge=1
                    )
                )
            )
        )
        
        try:
            response = messaging.send_multicast(message, app=self.app)
            
            # 실패한 토큰 처리 (만료된 토큰 등)
            if response.failure_count > 0:
                invalid_tokens = []
                for idx, result in enumerate(response.responses):
                    if not result.success:
                        invalid_tokens.append(fcm_tokens[idx])
                
                # 만료된 토큰은 DB에서 비활성화
                self._deactivate_invalid_tokens(invalid_tokens)
            
            return {
                "success_count": response.success_count,
                "failure_count": response.failure_count,
                "total_count": len(fcm_tokens)
            }
        
        except Exception as e:
            return {
                "success_count": 0,
                "failure_count": len(fcm_tokens),
                "total_count": len(fcm_tokens),
                "error": str(e)
            }
    
    def _deactivate_invalid_tokens(self, invalid_tokens: List[str]):
        """만료되거나 유효하지 않은 토큰 비활성화"""
        if not invalid_tokens:
            return
        
        from ..models import FcmToken
        self.db.query(FcmToken).filter(
            FcmToken.fcm_token.in_(invalid_tokens)
        ).update({"is_active": 0})
        self.db.commit()

