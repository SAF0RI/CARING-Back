import io
import tempfile
import os
from typing import Dict, Any, Optional
from google.cloud import speech
from google.oauth2 import service_account
import librosa
import numpy as np


class GoogleSTTService:
    def __init__(self):
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Google Cloud Speech-to-Text 클라이언트 초기화"""
        try:
            # 환경변수에서 서비스 계정 키 파일 경로 가져오기
            credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            
            if credentials_path and os.path.exists(credentials_path):
                # 서비스 계정 키 파일로 인증
                credentials = service_account.Credentials.from_service_account_file(
                    credentials_path,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
                self.client = speech.SpeechClient(credentials=credentials)
            else:
                # 기본 인증 (환경변수 GOOGLE_APPLICATION_CREDENTIALS 설정됨)
                self.client = speech.SpeechClient()
                
        except Exception as e:
            print(f"Google STT 클라이언트 초기화 실패: {e}")
            self.client = None
    
    def transcribe_audio(self, audio_file, language_code: str = "ko-KR") -> Dict[str, Any]:
        """
        음성 파일을 텍스트로 변환합니다.
        
        Args:
            audio_file: 업로드된 음성 파일 (FastAPI UploadFile)
            language_code: 언어 코드 (기본값: ko-KR)
            
        Returns:
            Dict: STT 결과
        """
        if not self.client:
            return {
                "error": "Google STT 클라이언트가 초기화되지 않았습니다",
                "transcript": "",
                "confidence": 0.0
            }
        
        try:
            # 임시 파일로 저장
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                content = audio_file.file.read()
                audio_file.file.seek(0)
                tmp_file.write(content)
                tmp_file_path = tmp_file.name
            
            # 오디오 파일 로드 및 전처리
            audio_data, sample_rate = librosa.load(tmp_file_path, sr=16000)
            
            # 오디오 데이터를 bytes로 변환
            audio_data = np.clip(audio_data, -1.0, 1.0)
            audio_bytes = (audio_data * 32767).astype('int16').tobytes()
            
            # Google Cloud Speech-to-Text 요청 구성
            audio = speech.RecognitionAudio(content=audio_bytes)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=sample_rate,
                language_code=language_code,
                enable_automatic_punctuation=True,
                enable_word_time_offsets=True,
                model="latest_long",  # 최신 장시간 모델 사용
            )
            
            # STT 요청 실행
            response = self.client.recognize(config=config, audio=audio)
            
            # 결과 처리
            if response.results:
                result = response.results[0]
                transcript = result.alternatives[0].transcript
                confidence = result.alternatives[0].confidence
                
                return {
                    "transcript": transcript,
                    "confidence": confidence,
                    "language_code": language_code,
                    "audio_duration": len(audio_data) / sample_rate,
                    "sample_rate": sample_rate
                }
            else:
                return {
                    "error": "음성을 인식할 수 없습니다",
                    "transcript": "",
                    "confidence": 0.0
                }
                
        except Exception as e:
            return {
                "error": f"STT 처리 중 오류 발생: {str(e)}",
                "transcript": "",
                "confidence": 0.0
            }
        finally:
            # 임시 파일 정리
            try:
                os.unlink(tmp_file_path)
            except OSError as e:
+                print("임시 파일 삭제 실패: %s", tmp_file_path, exc_info=True)


# 전역 인스턴스
stt_service = GoogleSTTService()


def transcribe_voice(audio_file, language_code: str = "ko-KR") -> Dict[str, Any]:
    """음성을 텍스트로 변환하는 함수"""
    return stt_service.transcribe_audio(audio_file, language_code)
