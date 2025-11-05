"""FCM 알림 전송 서비스"""
import os
import json
import logging
from typing import List, Dict, Optional
from firebase_admin import credentials, messaging, initialize_app
from sqlalchemy.orm import Session
from ..repositories.fcm_repo import get_active_fcm_tokens_by_user, get_active_fcm_tokens_by_username


# Firebase Admin SDK 초기화 (싱글톤 패턴)
_firebase_app = None

# 로거 설정
logger = logging.getLogger(__name__)


def _get_firebase_app():
    """Firebase Admin SDK 앱 인스턴스 가져오기 (초기화는 최초 1회만)"""
    global _firebase_app
    
    logger.info("[Firebase] _get_firebase_app() 호출됨")
    
    if _firebase_app is None:
        logger.info("[Firebase] Firebase 앱 초기화 시작")
        
        try:
            # 환경 변수에서 Firebase 인증 정보 가져오기
            firebase_cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
            cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
            
            logger.info(f"[Firebase] 환경 변수 확인 - FIREBASE_CREDENTIALS_JSON: {'설정됨' if firebase_cred_json else '없음'}")
            logger.info(f"[Firebase] 환경 변수 확인 - FIREBASE_CREDENTIALS_PATH: {cred_path}")
            
            # 하드코딩된 경로 사용 (환경 변수가 없을 경우)
            if not cred_path and not firebase_cred_json:
                cred_path = "/home/ubuntu/caring-voice/sapori-2025-firebase-adminsdk-fbsvc-2e736ed406.json"
                logger.info(f"[Firebase] 환경 변수 없음, 하드코딩된 경로 사용: {cred_path}")
            
            # JSON 문자열로 제공되는 경우
            if firebase_cred_json:
                logger.info("[Firebase] JSON 문자열에서 인증서 로드 시도")
                try:
                    cred_dict = json.loads(firebase_cred_json)
                    cred = credentials.Certificate(cred_dict)
                    logger.info("[Firebase] JSON 문자열에서 인증서 로드 성공")
                except json.JSONDecodeError as e:
                    logger.error(f"[Firebase] JSON 파싱 실패: {str(e)}")
                    raise ValueError(f"Invalid JSON in FIREBASE_CREDENTIALS_JSON: {str(e)}")
                except Exception as e:
                    logger.error(f"[Firebase] JSON 인증서 생성 실패: {str(e)}")
                    logger.exception("[Firebase] 상세 에러:")
                    raise
            # 파일 경로로 제공되는 경우
            elif cred_path:
                logger.info(f"[Firebase] 파일 경로에서 인증서 로드 시도: {cred_path}")
                
                if not os.path.exists(cred_path):
                    logger.error(f"[Firebase] 인증서 파일이 존재하지 않음: {cred_path}")
                    raise ValueError(
                        f"Firebase credentials file not found at: {cred_path}. "
                        "Set FIREBASE_CREDENTIALS_JSON or FIREBASE_CREDENTIALS_PATH environment variable."
                    )
                
                logger.info(f"[Firebase] 인증서 파일 존재 확인 완료: {cred_path}")
                
                try:
                    cred = credentials.Certificate(cred_path)
                    logger.info("[Firebase] 인증서 파일 로드 성공")
                except Exception as e:
                    logger.error(f"[Firebase] 인증서 파일 로드 실패: {str(e)}")
                    logger.exception("[Firebase] 상세 에러:")
                    raise
            else:
                logger.error("[Firebase] Firebase 인증 정보가 제공되지 않음")
                raise ValueError(
                    "Firebase credentials not found. "
                    "Set FIREBASE_CREDENTIALS_JSON or FIREBASE_CREDENTIALS_PATH environment variable."
                )
            
            # Firebase 앱 초기화
            logger.info("[Firebase] Firebase 앱 초기화 시도")
            try:
                _firebase_app = initialize_app(cred)
                logger.info("[Firebase] Firebase 앱 초기화 성공")
            except Exception as e:
                logger.error(f"[Firebase] Firebase 앱 초기화 실패: {str(e)}")
                logger.exception("[Firebase] 상세 에러:")
                raise
                
        except ValueError as e:
            logger.error(f"[Firebase] ValueError 발생: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"[Firebase] 예상치 못한 오류 발생: {type(e).__name__}: {str(e)}")
            logger.exception("[Firebase] 상세 에러:")
            raise
    else:
        logger.debug("[Firebase] 이미 초기화된 Firebase 앱 반환")
    
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
            # firebase-admin 7.x에서는 send_each_for_multicast 사용
            response = messaging.send_each_for_multicast(message, app=self.app)
            
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

    def send_notification_to_tokens(
        self,
        tokens: List[str],
        title: str,
        body: str,
        data: Optional[Dict[str, str]] = None
    ) -> Dict[str, int]:
        """원시 토큰 배열로 테스트 전송"""
        return self._send_multicast(tokens, title, body, data)
    
    def _deactivate_invalid_tokens(self, invalid_tokens: List[str]):
        """만료되거나 유효하지 않은 토큰 비활성화"""
        if not invalid_tokens:
            return
        
        from ..models import FcmToken
        self.db.query(FcmToken).filter(
            FcmToken.fcm_token.in_(invalid_tokens)
        ).update({"is_active": 0}, synchronize_session=False)
        self.db.commit()

