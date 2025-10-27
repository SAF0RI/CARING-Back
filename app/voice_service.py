import os
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import UploadFile, HTTPException
from io import BytesIO
import librosa
from .s3_service import upload_fileobj
from .stt_service import transcribe_voice
from .constants import VOICE_BASE_PREFIX, DEFAULT_UPLOAD_FOLDER
from .db_service import get_db_service
from .auth_service import get_auth_service


class VoiceService:
    """음성 관련 서비스"""
    
    def __init__(self, db: Session):
        self.db = db
        self.db_service = get_db_service(db)
        self.auth_service = get_auth_service(db)
    
    async def upload_user_voice(self, file: UploadFile, username: str, language_code: str = "ko-KR") -> Dict[str, Any]:
        """
        사용자 음성 파일 업로드 (S3 + DB 저장 + STT)
        
        Args:
            file: 업로드된 음성 파일
            username: 사용자 아이디
            language_code: 언어 코드
            
        Returns:
            dict: 업로드 결과
        """
        try:
            # 1. 사용자 조회
            user = self.auth_service.get_user_by_username(username)
            if not user:
                return {
                    "success": False,
                    "message": "User not found"
                }
            
            # 2. 파일 확장자 검증
            if not file.filename.endswith('.wav'):
                return {
                    "success": False,
                    "message": "Only .wav files are allowed"
                }
            
            # 3. S3 업로드
            bucket = os.getenv("S3_BUCKET_NAME")
            if not bucket:
                return {
                    "success": False,
                    "message": "S3_BUCKET_NAME not configured"
                }
            
            file_content = await file.read()
            base_prefix = VOICE_BASE_PREFIX.rstrip("/")
            effective_prefix = f"{base_prefix}/{DEFAULT_UPLOAD_FOLDER}".rstrip("/")
            key = f"{effective_prefix}/{file.filename}"
            
            file_obj_for_s3 = BytesIO(file_content)
            upload_fileobj(bucket=bucket, key=key, fileobj=file_obj_for_s3)
            
            # 4. STT 변환
            file_obj_for_stt = BytesIO(file_content)
            
            class TempUploadFile:
                def __init__(self, content, filename):
                    self.file = content
                    self.filename = filename
                    self.content_type = "audio/wav"
            
            stt_file = TempUploadFile(file_obj_for_stt, file.filename)
            stt_result = transcribe_voice(stt_file, language_code)
            
            # 5. 데이터베이스 저장
            duration_ms = int(stt_result.get("audio_duration", 0) * 1000) if stt_result.get("audio_duration") else 0
            sample_rate = stt_result.get("sample_rate", 16000)
            
            # Voice 저장
            voice = self.db_service.create_voice(
                voice_key=key,
                voice_name=file.filename,
                duration_ms=duration_ms,
                user_id=user.user_id,
                sample_rate=sample_rate
            )
            
            # VoiceContent 저장 (STT 결과)
            if stt_result.get("transcript"):
                self.db_service.create_voice_content(
                    voice_id=voice.voice_id,
                    content=stt_result["transcript"],
                    locale=language_code,
                    provider="google",
                    confidence_bps=int(stt_result.get("confidence", 0) * 10000)
                )
            
            return {
                "success": True,
                "message": "음성 파일이 성공적으로 업로드되었습니다.",
                "voice_id": voice.voice_id
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"업로드 실패: {str(e)}"
            }


def get_voice_service(db: Session) -> VoiceService:
    """음성 서비스 인스턴스 생성"""
    return VoiceService(db)
