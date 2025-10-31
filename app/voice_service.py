import os
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from fastapi import UploadFile, HTTPException
from io import BytesIO
import asyncio
import tempfile
import librosa
import soundfile as sf
import numpy as np
from .s3_service import upload_fileobj, get_presigned_url
from .stt_service import transcribe_voice
from .nlp_service import analyze_text_sentiment
from .emotion_service import analyze_voice_emotion
from .constants import VOICE_BASE_PREFIX, DEFAULT_UPLOAD_FOLDER
from .db_service import get_db_service
from .auth_service import get_auth_service
from .repositories.job_repo import ensure_job_row, mark_text_done, mark_audio_done, try_aggregate


class VoiceService:
    """음성 관련 서비스"""
    
    def __init__(self, db: Session):
        self.db = db
        self.db_service = get_db_service(db)
        self.auth_service = get_auth_service(db)
    
    def _convert_to_wav(self, file_content: bytes, original_filename: str) -> Tuple[bytes, str]:
        """Convert any audio to WAV format (16kHz, mono)"""
        tmp_input = None
        tmp_output = None
        try:
            ext = original_filename.rsplit('.', 1)[-1].lower() if '.' in original_filename else 'wav'
            tmp_input = tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False)
            tmp_input.write(file_content)
            tmp_input.flush()

            audio, sr = librosa.load(tmp_input.name, sr=16000, mono=True)
            audio = np.clip(audio, -1.0, 1.0)

            tmp_output = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            sf.write(tmp_output.name, audio, 16000, format='WAV')

            with open(tmp_output.name, 'rb') as f:
                wav_bytes = f.read()

            base_name = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename
            wav_filename = f"{base_name}.wav"

            return wav_bytes, wav_filename
        finally:
            if tmp_input:
                try:
                    os.unlink(tmp_input.name)
                except:
                    pass
            if tmp_output:
                try:
                    os.unlink(tmp_output.name)
                except:
                    pass
    
    async def upload_user_voice(self, file: UploadFile, username: str) -> Dict[str, Any]:
        """
        사용자 음성 파일 업로드 (S3 + DB 저장)
        모든 파일은 WAV로 변환 후 처리
        
        Args:
            file: 업로드된 음성 파일
            username: 사용자 아이디
            
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
            if not (file.filename.endswith('.wav') or file.filename.endswith('.m4a')):
                return {
                    "success": False,
                    "message": "Only .wav and .m4a files are allowed"
                }
            
            # 3. 파일 읽기 및 WAV 변환
            file_content = await file.read()
            wav_content, wav_filename = self._convert_to_wav(file_content, file.filename)
            
            # 4. S3 업로드 (WAV 파일)
            bucket = os.getenv("S3_BUCKET_NAME")
            if not bucket:
                return {
                    "success": False,
                    "message": "S3_BUCKET_NAME not configured"
                }
            
            base_prefix = VOICE_BASE_PREFIX.rstrip("/")
            effective_prefix = f"{base_prefix}/{DEFAULT_UPLOAD_FOLDER}".rstrip("/")
            key = f"{effective_prefix}/{wav_filename}"
            
            file_obj_for_s3 = BytesIO(wav_content)
            upload_fileobj(bucket=bucket, key=key, fileobj=file_obj_for_s3)
            
            # 5. 데이터베이스 저장 (기본 정보만)
            # 파일 크기로 대략적인 duration 추정
            file_size_mb = len(wav_content) / (1024 * 1024)
            estimated_duration_ms = int(file_size_mb * 1000)  # 대략적인 추정
            
            # Voice 저장 (STT 없이 기본 정보만)
            voice = self.db_service.create_voice(
                voice_key=key,
                voice_name=wav_filename,
                duration_ms=estimated_duration_ms,
                user_id=user.user_id,
                sample_rate=16000  # 기본값
            )
            # ensure job row
            ensure_job_row(self.db, voice.voice_id)
            
            # 6. 비동기 후처리 (STT→NLP, 음성 감정 분석) - WAV 데이터 사용
            asyncio.create_task(self._process_stt_and_nlp_background(wav_content, wav_filename, voice.voice_id))
            asyncio.create_task(self._process_audio_emotion_background(wav_content, wav_filename, voice.voice_id))
            
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
    
    async def _process_stt_and_nlp_background(self, file_content: bytes, filename: str, voice_id: int):
        """STT → NLP 순차 처리 (백그라운드 비동기)"""
        try:
            # 1. STT 처리
            file_obj_for_stt = BytesIO(file_content)
            
            class TempUploadFile:
                def __init__(self, content, filename):
                    self.file = content
                    self.filename = filename
                    self.content_type = "audio/m4a" if filename.endswith('.m4a') else "audio/wav"
            
            stt_file = TempUploadFile(file_obj_for_stt, filename)
            stt_result = transcribe_voice(stt_file, "ko-KR")
            
            if not stt_result.get("transcript"):
                print(f"STT 변환 실패: voice_id={voice_id}")
                return
            
            transcript = stt_result["transcript"]
            confidence = stt_result.get("confidence", 0)
            
            # 2. NLP 감정 분석 (STT 결과로)
            nlp_result = analyze_text_sentiment(transcript, "ko")
            
            # 3. VoiceContent 저장 (STT 결과 + NLP 감정 분석 결과)
            score_bps = None
            magnitude_x1000 = None
            
            if "sentiment" in nlp_result and nlp_result["sentiment"]:
                sentiment = nlp_result["sentiment"]
                score_bps = int(sentiment.get("score", 0) * 10000)  # -10000~10000
                magnitude = sentiment.get("magnitude", 0)
                magnitude_x1000 = int(magnitude * 1000)  # 0~?
            
            self.db_service.create_voice_content(
                voice_id=voice_id,
                content=transcript,
                score_bps=score_bps,
                magnitude_x1000=magnitude_x1000,
                locale="ko-KR",
                provider="google",
                confidence_bps=int(confidence * 10000)
            )
            # mark text done and try aggregate
            mark_text_done(self.db, voice_id)
            try_aggregate(self.db, voice_id)
            
            print(f"STT → NLP 처리 완료: voice_id={voice_id}")
            
        except Exception as e:
            print(f"STT → NLP 처리 중 오류 발생: {e}")

    async def _process_audio_emotion_background(self, file_content: bytes, filename: str, voice_id: int):
        """음성 파일 자체의 감정 분석을 백그라운드에서 수행하여 voice_analyze 저장"""
        try:
            file_obj = BytesIO(file_content)

            class TempUploadFile:
                def __init__(self, content, filename):
                    self.file = content
                    self.filename = filename
                    self.content_type = "audio/m4a" if filename.endswith('.m4a') else "audio/wav"

            emotion_file = TempUploadFile(file_obj, filename)
            result = analyze_voice_emotion(emotion_file)

            # 디버그 로그: 전체 결과 요약
            try:
                top_em = result.get('top_emotion') or result.get('emotion')
                conf = result.get('confidence')
                mv = result.get('model_version')
                em_scores = result.get('emotion_scores') or {}
                print(f"[emotion] result voice_id={voice_id} top={top_em} conf={conf} model={mv} scores={{{k: round(float(v),4) for k,v in em_scores.items()}}}", flush=True)
            except Exception:
                pass

            def to_bps(v: float) -> int:
                try:
                    return max(0, min(10000, int(round(float(v) * 10000))))
                except Exception:
                    return 0

            probs = result.get("emotion_scores", {})
            happy = to_bps(probs.get("happy", probs.get("happiness", 0)))
            sad = to_bps(probs.get("sad", probs.get("sadness", 0)))
            neutral = to_bps(probs.get("neutral", 0))
            angry = to_bps(probs.get("angry", probs.get("anger", 0)))
            fear = to_bps(probs.get("fear", probs.get("fearful", 0)))
            surprise = to_bps(probs.get("surprise", probs.get("surprised", 0)))

            # 모델 응답 키 보정: emotion_service는 기본적으로 "emotion"을 반환
            top_emotion = result.get("top_emotion") or result.get("label") or result.get("emotion")
            top_conf = result.get("top_confidence") or result.get("confidence", 0)
            top_conf_bps = to_bps(top_conf)
            model_version = result.get("model_version")
            if isinstance(model_version, str) and len(model_version) > 32:
                model_version = model_version[:32]

            total_raw = happy + sad + neutral + angry + fear + surprise
            print(f"[voice_analyze] ROUND 이전: happy={happy}, sad={sad}, neutral={neutral}, angry={angry}, fear={fear}, surprise={surprise} → 합계={total_raw}")
            if total_raw == 0:
                # 모델이 확률을 반환하지 못한 경우: 중립 100%
                print(f"[voice_analyze] 확률 없음: 모두 0 → neutral=10000")
                happy, sad, neutral, angry, fear, surprise = 0, 0, 10000, 0, 0, 0
            else:
                # 비율 보정(라운딩 후 합 10000로 맞춤)
                scale = 10000 / float(total_raw)
                before_vals = {
                    "happy": happy, "sad": sad, "neutral": neutral, 
                    "angry": angry, "fear": fear, "surprise": surprise,
                }
                vals = {
                    "happy": int(round(happy * scale)),
                    "sad": int(round(sad * scale)),
                    "neutral": int(round(neutral * scale)),
                    "angry": int(round(angry * scale)),
                    "fear": int(round(fear * scale)),
                    "surprise": int(round(surprise * scale)),
                }
                print(f"[voice_analyze] ROUND: raw={before_vals} scale={scale:.5f} → after={vals}")
                diff = 10000 - sum(vals.values())
                if diff != 0:
                    # 가장 큰 항목에 차이를 보정(음수/양수 모두 처리)
                    key_max = max(vals, key=lambda k: vals[k])
                    print(f"[voice_analyze] DIFF 보정: {diff} → max_emotion={key_max} ({vals[key_max]}) before")
                    vals[key_max] = max(0, min(10000, vals[key_max] + diff))
                    print(f"[voice_analyze] DIFF 보정: {diff} → max_emotion={key_max} after={vals[key_max]}")
                happy, sad, neutral, angry, fear, surprise = (
                    vals["happy"], vals["sad"], vals["neutral"], vals["angry"], vals["fear"], vals["surprise"]
                )

            # DB 저장 직전 값 로깅
            try:
                print(
                    f"[voice_analyze] to_db voice_id={voice_id} "
                    f"vals={{'happy': {happy}, 'sad': {sad}, 'neutral': {neutral}, 'angry': {angry}, 'fear': {fear}, 'surprise': {surprise}}} "
                    f"top={top_emotion} conf_bps={top_conf_bps} model={model_version}"
                )
            except Exception:
                pass

            self.db_service.create_voice_analyze(
                voice_id=voice_id,
                happy_bps=happy,
                sad_bps=sad,
                neutral_bps=neutral,
                angry_bps=angry,
                fear_bps=fear,
                surprise_bps=surprise,
                top_emotion=top_emotion,
                top_confidence_bps=top_conf_bps,
                model_version=model_version,
            )
            # mark audio done and try aggregate
            mark_audio_done(self.db, voice_id)
            try_aggregate(self.db, voice_id)
            print(f"[voice_analyze] saved voice_id={voice_id} top={top_emotion} conf_bps={top_conf_bps}", flush=True)
        except Exception as e:
            print(f"Audio emotion background error: {e}", flush=True)
    
    def get_user_voice_list(self, username: str) -> Dict[str, Any]:
        """
        사용자 음성 리스트 조회
        
        Args:
            username: 사용자 아이디
            
        Returns:
            dict: 음성 리스트
        """
        try:
            # 1. 사용자 조회
            user = self.auth_service.get_user_by_username(username)
            if not user:
                return {
                    "success": False,
                    "voices": []
                }
            
            # 2. 사용자의 음성 목록 조회
            voices = self.db_service.get_voices_by_user(user.user_id)
            
            # S3 버킷 정보
            bucket = os.getenv("S3_BUCKET_NAME")
            
            voice_list = []
            for voice in voices:
                # 생성 날짜
                created_at = voice.created_at.isoformat() if voice.created_at else ""
                
                # 감정 (voice_analyze에서 top_emotion 가져오기)
                emotion = None
                if voice.voice_analyze:
                    emotion = voice.voice_analyze.top_emotion
                
                # 질문 제목 (voice_question -> question.content)
                question_title = None
                # voice는 이미 relationship으로 questions를 가지고 있음
                if voice.questions:
                    question_title = voice.questions[0].content
                
                # 음성 내용
                content = "아직 기록이 완성되지 않았습니다"
                if voice.voice_content and voice.voice_content.content:
                    content = voice.voice_content.content
                
                # S3 URL 생성
                s3_url = None
                if bucket and voice.voice_key:
                    s3_url = get_presigned_url(bucket, voice.voice_key, expires_in=3600)
                
                voice_list.append({
                    "voice_id": voice.voice_id,
                    "created_at": created_at,
                    "emotion": emotion,
                    "question_title": question_title,
                    "content": content,
                    "s3_url": s3_url
                })
            
            return {
                "success": True,
                "voices": voice_list
            }
            
        except Exception as e:
            return {
                "success": False,
                "voices": []
            }

    def get_care_voice_list(self, care_username: str, skip: int = 0, limit: int = 20) -> Dict[str, Any]:
        """보호자 페이지: 연결된 사용자의 분석 완료 음성 목록 조회(페이징)"""
        try:
            voices = self.db_service.get_care_voices(care_username, skip=skip, limit=limit)
            items = []
            for v in voices:
                created_at = v.created_at.isoformat() if v.created_at else ""
                emotion = v.voice_analyze.top_emotion if v.voice_analyze else None
                items.append({
                    "voice_id": v.voice_id,
                    "created_at": created_at,
                    "emotion": emotion,
                })
            return {"success": True, "voices": items}
        except Exception:
            return {"success": False, "voices": []}

    def get_user_voice_detail(self, voice_id: int, username: str) -> Dict[str, Any]:
        """voice_id와 username으로 상세 정보 조회"""
        try:
            voice = self.db_service.get_voice_detail_for_username(voice_id, username)
            if not voice:
                return {"success": False, "error": "Voice not found or not owned by user"}

            title = None
            if voice.questions:
                title = voice.questions[0].content

            top_emotion = None
            if voice.voice_analyze:
                top_emotion = voice.voice_analyze.top_emotion

            created_at = voice.created_at.isoformat() if voice.created_at else ""

            voice_content = None
            if voice.voice_content:
                voice_content = voice.voice_content.content

            # S3 URL 생성
            bucket = os.getenv("S3_BUCKET_NAME")
            s3_url = None
            if bucket and voice.voice_key:
                s3_url = get_presigned_url(bucket, voice.voice_key, expires_in=3600)

            return {
                "success": True,
                "title": title,
                "top_emotion": top_emotion,
                "created_at": created_at,
                "voice_content": voice_content,
                "s3_url": s3_url,
            }
        except Exception:
            return {"success": False, "error": "Failed to fetch voice detail"}

    def delete_user_voice(self, voice_id: int, username: str) -> Dict[str, Any]:
        """사용자 소유 검증 후 음성 및 연관 데이터 삭제"""
        try:
            voice = self.db_service.get_voice_owned_by_username(voice_id, username)
            if not voice:
                return {"success": False, "message": "Voice not found or not owned by user"}

            ok = self.db_service.delete_voice_with_relations(voice_id)
            if not ok:
                return {"success": False, "message": "Delete failed"}
            return {"success": True, "message": "Deleted"}
        except Exception as e:
            return {"success": False, "message": f"Delete error: {str(e)}"}
    
    async def upload_voice_with_question(self, file: UploadFile, username: str, question_id: int) -> Dict[str, Any]:
        """
        질문과 함께 음성 파일 업로드 (S3 + DB 저장 + STT + voice_question 매핑)
        모든 파일은 WAV로 변환 후 처리
        
        Args:
            file: 업로드된 음성 파일
            username: 사용자 아이디
            question_id: 질문 ID
            
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
            
            # 2. 질문 조회
            question = self.db_service.get_question_by_id(question_id)
            if not question:
                return {
                    "success": False,
                    "message": "Question not found"
                }
            
            # 3. 파일 확장자 검증
            if not (file.filename.endswith('.wav') or file.filename.endswith('.m4a')):
                return {
                    "success": False,
                    "message": "Only .wav and .m4a files are allowed"
                }
            
            # 4. 파일 읽기 및 WAV 변환
            file_content = await file.read()
            wav_content, wav_filename = self._convert_to_wav(file_content, file.filename)
            
            # 5. S3 업로드 (WAV 파일)
            bucket = os.getenv("S3_BUCKET_NAME")
            if not bucket:
                return {
                    "success": False,
                    "message": "S3_BUCKET_NAME not configured"
                }
            
            base_prefix = VOICE_BASE_PREFIX.rstrip("/")
            effective_prefix = f"{base_prefix}/{DEFAULT_UPLOAD_FOLDER}".rstrip("/")
            key = f"{effective_prefix}/{wav_filename}"
            
            file_obj_for_s3 = BytesIO(wav_content)
            upload_fileobj(bucket=bucket, key=key, fileobj=file_obj_for_s3)
            
            # 6. 데이터베이스 저장 (기본 정보만)
            file_size_mb = len(wav_content) / (1024 * 1024)
            estimated_duration_ms = int(file_size_mb * 1000)
            
            voice = self.db_service.create_voice(
                voice_key=key,
                voice_name=wav_filename,
                duration_ms=estimated_duration_ms,
                user_id=user.user_id,
                sample_rate=16000
            )
            # ensure job row
            ensure_job_row(self.db, voice.voice_id)
            
            # 7. 비동기 후처리 (STT→NLP, 음성 감정 분석) - WAV 데이터 사용
            asyncio.create_task(self._process_stt_and_nlp_background(wav_content, wav_filename, voice.voice_id))
            asyncio.create_task(self._process_audio_emotion_background(wav_content, wav_filename, voice.voice_id))
            
            # 8. Voice-Question 매핑 저장
            self.db_service.link_voice_question(voice.voice_id, question_id)
            
            return {
                "success": True,
                "message": "음성 파일과 질문이 성공적으로 업로드되었습니다.",
                "voice_id": voice.voice_id,
                "question_id": question_id
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"업로드 실패: {str(e)}"
            }


def get_voice_service(db: Session) -> VoiceService:
    """음성 서비스 인스턴스 생성"""
    return VoiceService(db)
