import os
import time
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from fastapi import UploadFile, HTTPException
from io import BytesIO
import asyncio
import tempfile
import subprocess
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
from .performance_logger import get_performance_logger, clear_logger
from sqlalchemy import func, extract
from .models import VoiceAnalyze, Voice, VoiceComposite
from datetime import datetime
from calendar import monthrange
from collections import Counter, defaultdict


class VoiceService:
    """음성 관련 서비스"""
    
    def __init__(self, db: Session):
        self.db = db
        self.db_service = get_db_service(db)
        self.auth_service = get_auth_service(db)
    
    def _convert_to_wav(self, file_content: bytes, original_filename: str) -> Tuple[bytes, str]:
        """
        Convert any audio to WAV format (16kHz, mono)
        최적화: ffmpeg 직접 사용 + stdin/stdout 파이프로 임시 파일 제거
        """
        ext = original_filename.rsplit('.', 1)[-1].lower() if '.' in original_filename else 'wav'
        base_name = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename
        wav_filename = f"{base_name}.wav"
        
        # 입력 파일 크기 검증 (최소 크기 확인)
        if len(file_content) < 100:
            print(f"[convert] 입력 파일이 너무 작음: {len(file_content)} bytes, librosa로 폴백")
            # 바로 librosa로 폴백 (아래 코드로 계속 진행)
        
        # 방법 1: ffmpeg subprocess 직접 사용 (가장 빠름, stdin/stdout 파이프)
        if len(file_content) >= 100:  # 충분한 크기일 때만 시도
            try:
                ffmpeg_cmd = [
                    'ffmpeg',
                    '-i', 'pipe:0',  # stdin에서 입력
                    '-f', 'wav',      # WAV 형식
                    '-ar', '16000',   # 16kHz 샘플링 레이트
                    '-ac', '1',       # 모노 (1채널)
                    '-acodec', 'pcm_s16le',  # 16-bit PCM
                    '-loglevel', 'error',  # 에러만 출력
                    '-y',             # 덮어쓰기
                    'pipe:1'          # stdout으로 출력
                ]
                
                process = subprocess.run(
                    ffmpeg_cmd,
                    input=file_content,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=30,  # 타임아웃 30초
                    check=False
                )
                
                # 출력 데이터 유효성 검사
                output_size = len(process.stdout) if process.stdout else 0
                
                # WAV 파일은 최소 헤더(44 bytes) + 데이터 필요
                # 16kHz 모노 기준 0.1초도 약 3.2KB 필요 (16kHz * 2 bytes * 0.1초 = 3.2KB)
                if process.returncode == 0 and process.stdout and output_size > 3200:
                    # 추가 검증: WAV 헤더 확인 (RIFF 헤더)
                    if process.stdout[:4] == b'RIFF' and process.stdout[8:12] == b'WAVE':
                        print(f"[convert] ffmpeg success: input={len(file_content)} bytes, output={output_size} bytes")
                        return process.stdout, wav_filename
                    else:
                        print(f"[convert] ffmpeg output invalid WAV header, falling back to librosa")
                else:
                    # ffmpeg 실패 또는 출력이 너무 작음
                    stderr_msg = process.stderr.decode('utf-8', errors='ignore')[:500] if process.stderr else "unknown"
                    print(f"[convert] ffmpeg failed or invalid output (returncode={process.returncode}, input={len(file_content)} bytes, output={output_size} bytes)")
                    print(f"[convert] stderr: {stderr_msg[:200]}")
            except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
                # ffmpeg가 없거나 실패 시 기존 방식으로 폴백
                print(f"[convert] ffmpeg not available or failed ({type(e).__name__}): {str(e)[:200]}, using librosa fallback")
        
        # 방법 2: 기존 librosa 방식 (폴백)
        tmp_input = None
        tmp_output = None
        try:
            tmp_input = tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False)
            tmp_input.write(file_content)
            tmp_input.flush()

            audio, sr = librosa.load(tmp_input.name, sr=16000, mono=True)
            
            # 오디오 길이 검증 (최소 0.1초 이상)
            if len(audio) == 0 or len(audio) / sr < 0.1:
                raise ValueError(f"변환된 오디오가 너무 짧거나 비어있음: {len(audio)} samples, {len(audio)/sr:.3f} seconds")
            
            audio = np.clip(audio, -1.0, 1.0)

            tmp_output = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            sf.write(tmp_output.name, audio, 16000, format='WAV')

            with open(tmp_output.name, 'rb') as f:
                wav_bytes = f.read()
            
            # 최종 출력 검증
            if len(wav_bytes) < 3200:
                raise ValueError(f"변환된 WAV 파일이 너무 작음: {len(wav_bytes)} bytes")

            print(f"[convert] librosa success: input={len(file_content)} bytes, output={len(wav_bytes)} bytes, audio_duration={len(audio)/sr:.3f}s")
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
        logger = None
        try:
            # 성능 추적 시작
            logger = get_performance_logger(0)  # voice_id는 나중에 설정
            logger.log_step("시작")
            
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
            
            # 3. 파일 읽기 및 WAV 변환 (비동기로 처리하여 블로킹 방지)
            file_content = await file.read()
            # CPU 집약적 작업을 스레드 풀에서 실행
            wav_content, wav_filename = await asyncio.to_thread(
                self._convert_to_wav, file_content, file.filename
            )
            logger.log_step("파일변환 완료")
            
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
            logger.log_step("s3업로드 완료")
            
            # 5. 데이터베이스 저장 (기본 정보만)
            # 파일 크기로 대략적인 duration 추정
            with sf.SoundFile(BytesIO(wav_content)) as wav_file:
                frames = len(wav_file)
                sr = wav_file.samplerate
            estimated_duration_ms = int((frames / sr) * 1000)
            
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
            logger.log_step("데이터베이스 입력 완료")
            
            # logger를 voice_id로 다시 생성 (기존 시간 유지)
            original_start = logger.start_time
            clear_logger(0)
            logger = get_performance_logger(voice.voice_id, preserve_time=original_start)
            # 기존 단계들 복사
            for step in ["시작", "파일변환 완료", "s3업로드 완료", "데이터베이스 입력 완료"]:
                if step in logger.steps:
                    continue
                logger.steps[step] = time.time() - original_start
            logger.voice_id = voice.voice_id
            
            # 6. 비동기 후처리 (STT→NLP, 음성 감정 분석) - WAV 데이터 사용
            # 메모리 모니터링: 비동기 작업 시작 전
            from .memory_monitor import log_memory_info
            log_memory_info(f"Before async tasks - voice_id={voice.voice_id}")
            
            asyncio.create_task(self._process_stt_and_nlp_background(wav_content, wav_filename, voice.voice_id))
            asyncio.create_task(self._process_audio_emotion_background(wav_content, wav_filename, voice.voice_id))
            
            return {
                "success": True,
                "message": "음성 파일이 성공적으로 업로드되었습니다.",
                "voice_id": voice.voice_id
            }
        except Exception as e:
            if logger:
                logger.save_to_file()
                clear_logger(logger.voice_id or 0)
            return {
                "success": False,
                "message": f"업로드 실패: {str(e)}"
            }
    
    async def _process_stt_and_nlp_background(self, file_content: bytes, filename: str, voice_id: int):
        """STT → NLP 순차 처리 (백그라운드 비동기)"""
        logger = get_performance_logger(voice_id)
        # 비동기 작업은 독립적인 세션을 생성하여 사용
        from .database import SessionLocal
        db = SessionLocal()
        try:
            logger.log_step("(비동기 작업) STT 작업 시작", category="async")
            
            # 1. STT 처리 (스레드 풀에서 실행하여 실제 병렬 처리 가능)
            file_obj_for_stt = BytesIO(file_content)
            
            class TempUploadFile:
                def __init__(self, content, filename):
                    self.file = content
                    self.filename = filename
                    self.content_type = "audio/m4a" if filename.endswith('.m4a') else "audio/wav"
            
            stt_file = TempUploadFile(file_obj_for_stt, filename)
            # 동기 함수를 스레드에서 실행하여 블로킹 방지 및 병렬 처리 가능
            stt_result = await asyncio.to_thread(transcribe_voice, stt_file, "ko-KR")
            
            if not stt_result.get("transcript"):
                print(f"STT 변환 실패: voice_id={voice_id}")
                return
            
            transcript = stt_result["transcript"]
            confidence = stt_result.get("confidence", 0)
            logger.log_step("stt 추출 완료", category="async")
            
            # 2. NLP 감정 분석 (STT 결과로) - 스레드에서 실행
            nlp_result = await asyncio.to_thread(analyze_text_sentiment, transcript, "ko")
            logger.log_step("nlp 작업 완료", category="async")
            
            # 3. VoiceContent 저장 (STT 결과 + NLP 감정 분석 결과)
            score_bps = None
            magnitude_x1000 = None
            
            if "sentiment" in nlp_result and nlp_result["sentiment"]:
                sentiment = nlp_result["sentiment"]
                score_bps = int(sentiment.get("score", 0) * 10000)  # -10000~10000
                magnitude = sentiment.get("magnitude", 0)
                magnitude_x1000 = int(magnitude * 1000)  # 0~?
            
            # 새로운 세션을 사용하여 DB 작업 수행
            db_service = get_db_service(db)
            db_service.create_voice_content(
                voice_id=voice_id,
                content=transcript,
                score_bps=score_bps,
                magnitude_x1000=magnitude_x1000,
                locale="ko-KR",
                provider="google",
                confidence_bps=int(confidence * 10000)
            )
            logger.log_step("데이터베이스 입력 완료 (STT/NLP)", category="async")
            
            # mark text done and try aggregate
            mark_text_done(db, voice_id)
            try_aggregate(db, voice_id)
            
            print(f"STT → NLP 처리 완료: voice_id={voice_id}")
            
        except Exception as e:
            print(f"STT → NLP 처리 중 오류 발생: {e}")
            db.rollback()
        finally:
            db.close()

    async def _process_audio_emotion_background(self, file_content: bytes, filename: str, voice_id: int):
        """음성 파일 자체의 감정 분석을 백그라운드에서 수행하여 voice_analyze 저장"""
        logger = get_performance_logger(voice_id)
        # 비동기 작업은 독립적인 세션을 생성하여 사용
        from .database import SessionLocal
        db = SessionLocal()
        try:
            logger.log_step("(비동기 작업) 모델 작업 시작", category="async")
            file_obj = BytesIO(file_content)

            class TempUploadFile:
                def __init__(self, content, filename):
                    self.file = content
                    self.filename = filename
                    self.content_type = "audio/m4a" if filename.endswith('.m4a') else "audio/wav"

            emotion_file = TempUploadFile(file_obj, filename)
            # CPU 집약적 작업을 스레드에서 실행하여 다른 요청과 병렬 처리 가능
            result = await asyncio.to_thread(analyze_voice_emotion, emotion_file)

            # 디버그 로그: 전체 결과 요약
            try:
                top_em = result.get('top_emotion') or result.get('emotion')
                conf = result.get('confidence')
                mv = result.get('model_version')
                em_scores = result.get('emotion_scores') or {}
                print(f"[emotion] result voice_id={voice_id} top={top_em} conf={conf} model={mv} scores={{{k: round(float(v),4) for k,v in em_scores.items()}}}", flush=True)
            except Exception:
                pass

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

            # 새로운 세션을 사용하여 DB 작업 수행
            db_service = get_db_service(db)
            db_service.create_voice_analyze(
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
            logger.log_step("모델 작업 완료", category="async")
            logger.log_step("데이터베이스 입력 완료 (모델)", category="async")
            
            # mark audio done and try aggregate
            mark_audio_done(db, voice_id)
            try_aggregate(db, voice_id)
            print(f"[voice_analyze] saved voice_id={voice_id} top={top_emotion} conf_bps={top_conf_bps}", flush=True)
        except Exception as e:
            print(f"Audio emotion background error: {e}", flush=True)
            db.rollback()
        finally:
            db.close()
    
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
                
                # 감정 (voice_composite에서 top_emotion 가져오기, 없으면 null)
                emotion = None
                if voice.voice_composite:
                    emotion = voice.voice_composite.top_emotion
                
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

    def get_care_voice_list(self, care_username: str, date: Optional[str] = None) -> Dict[str, Any]:
        """보호자 페이지: 연결된 사용자의 분석 완료 음성 목록 조회
        
        Args:
            care_username: 보호자 username
            date: 날짜 필터 (YYYY-MM-DD, Optional). None이면 전체 조회
        """
        try:
            voices = self.db_service.get_care_voices(care_username, date=date)
            items = []
            for v in voices:
                created_at = v.created_at.isoformat() if v.created_at else ""
                emotion = v.voice_composite.top_emotion if v.voice_composite else None
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
            if voice.voice_composite:
                top_emotion = voice.voice_composite.top_emotion

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
        logger = None
        try:
            # 성능 추적 시작
            logger = get_performance_logger(0)  # voice_id는 나중에 설정
            logger.log_step("시작")
            
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
            
            # 4. 파일 읽기 및 WAV 변환 (비동기로 처리하여 블로킹 방지)
            file_content = await file.read()
            # CPU 집약적 작업을 스레드 풀에서 실행
            wav_content, wav_filename = await asyncio.to_thread(
                self._convert_to_wav, file_content, file.filename
            )
            logger.log_step("파일변환 완료")
            
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
            logger.log_step("s3업로드 완료")
            
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
            logger.log_step("데이터베이스 입력 완료")
            
            # logger를 voice_id로 다시 생성 (기존 시간 유지)
            original_start = logger.start_time
            existing_steps = dict(logger.steps)
            existing_order = list(logger.step_order)
            existing_categories = dict(logger.step_category)
            
            clear_logger(0)
            logger = get_performance_logger(voice.voice_id, preserve_time=original_start)
            # 기존 단계들 복사 (order와 category 포함)
            for step in existing_order:
                elapsed = existing_steps[step]
                category = existing_categories.get(step, "serial")
                logger.add_step_with_time(step, elapsed, category)
            logger.voice_id = voice.voice_id
            
            # 7. 비동기 후처리 (STT→NLP, 음성 감정 분석) - WAV 데이터 사용
            # 메모리 모니터링: 비동기 작업 시작 전
            from .memory_monitor import log_memory_info
            log_memory_info(f"Before async tasks - voice_id={voice.voice_id}")
            
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
            if logger:
                logger.save_to_file()
                clear_logger(logger.voice_id or 0)
            return {
                "success": False,
                "message": f"업로드 실패: {str(e)}"
            }

    def get_user_emotion_monthly_frequency(self, username: str, month: str) -> Dict[str, Any]:
        """사용자 본인의 한달간 감정 빈도수 집계"""
        try:
            user = self.auth_service.get_user_by_username(username)
            if not user:
                return {"success": False, "frequency": {}, "message": "User not found"}
            try:
                y, m = map(int, month.split("-"))
            except Exception:
                return {"success": False, "frequency": {}, "message": "month format YYYY-MM required"}
            results = (
                self.db.query(VoiceComposite.top_emotion, func.count())
                .join(Voice, Voice.voice_id == VoiceComposite.voice_id)
                .filter(
                    Voice.user_id == user.user_id,
                    extract('year', Voice.created_at) == y,
                    extract('month', Voice.created_at) == m,
                    VoiceComposite.top_emotion.isnot(None)  # null 제외
                )
                .group_by(VoiceComposite.top_emotion)
                .all()
            )
            freq = {str(emotion): count for emotion, count in results if emotion}
            return {"success": True, "frequency": freq}
        except Exception as e:
            return {"success": False, "frequency": {}, "message": f"error: {str(e)}"}

    def get_user_emotion_weekly_summary(self, username: str, month: str, week: int) -> Dict[str, Any]:
        """사용자 본인의 월/주차별 요일별 top 감정 요약"""
        try:
            user = self.auth_service.get_user_by_username(username)
            if not user:
                return {"success": False, "weekly": [], "message": "User not found"}
            try:
                y, m = map(int, month.split("-"))
            except Exception:
                return {"success": False, "weekly": [], "message": "month format YYYY-MM required"}
            start_day = (week-1)*7+1
            end_day = min(week*7, monthrange(y, m)[1])
            start_date = datetime(y, m, start_day)
            end_date = datetime(y, m, end_day, 23, 59, 59)
            q = (
                self.db.query(Voice, VoiceComposite)
                .join(VoiceComposite, Voice.voice_id == VoiceComposite.voice_id)
                .filter(
                    Voice.user_id == user.user_id,
                    Voice.created_at >= start_date,
                    Voice.created_at <= end_date,
                ).order_by(Voice.created_at.asc())
            )
            days = defaultdict(list)
            day_first = {}
            for v, vc in q:
                d = v.created_at.date()
                em = vc.top_emotion if vc else None
                days[d].append(em)
                if d not in day_first:
                    day_first[d] = em
            result = []
            for d in sorted(days.keys()):
                cnt = Counter(days[d])
                # Unknown이 아닌 감정이 하나라도 있으면 Unknown 제외
                non_unknown_cnt = {k: v for k, v in cnt.items() if k and str(k).lower() not in ("unknown", "null", "none")}
                if non_unknown_cnt:
                    # Unknown 제외하고 top_emotion 선택
                    cnt_filtered = Counter(non_unknown_cnt)
                    top, val = cnt_filtered.most_common(1)[0]
                    top_emotions = [e for e, c in cnt_filtered.items() if c == val]
                    # day_first에서도 Unknown 제외된 감정 중 첫 번째 찾기
                    first_non_unknown = None
                    for em in days[d]:
                        if em and str(em).lower() not in ("unknown", "null", "none"):
                            first_non_unknown = em
                            break
                    selected = first_non_unknown if len(top_emotions) > 1 and first_non_unknown in top_emotions else top
                else:
                    # 모든 감정이 Unknown인 경우에만 Unknown 반환
                    top, val = cnt.most_common(1)[0]
                    top_emotions = [e for e, c in cnt.items() if c == val]
                    selected = day_first[d] if len(top_emotions) > 1 and day_first[d] in top_emotions else top
                result.append({
                    "date": d.isoformat(),
                    "weekday": d.strftime("%a"),
                    "top_emotion": selected
                })
            return {"success": True, "weekly": result}
        except Exception as e:
            return {"success": False, "weekly": [], "message": f"error: {str(e)}"}


def get_voice_service(db: Session) -> VoiceService:
    """음성 서비스 인스턴스 생성"""
    return VoiceService(db)
