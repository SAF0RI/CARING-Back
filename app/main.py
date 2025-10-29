import os
from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import JSONResponse
from typing import List
from .s3_service import upload_fileobj, list_bucket_objects
from .constants import VOICE_BASE_PREFIX, DEFAULT_UPLOAD_FOLDER
from .emotion_service import analyze_voice_emotion
from .stt_service import transcribe_voice
from .nlp_service import analyze_text_sentiment, analyze_text_entities, analyze_text_syntax
from .database import create_tables, engine, get_db
from .models import Base
from .auth_service import get_auth_service
from .voice_service import get_voice_service
from .dto import (
    SignupRequest, SignupResponse,
    SigninRequest, SigninResponse,
    UserVoiceUploadRequest, UserVoiceUploadResponse,
    VoiceQuestionUploadResponse,
    UserVoiceListResponse, UserVoiceDetailResponse,
    EmotionAnalysisResponse, TranscribeResponse,
    SentimentResponse, EntitiesResponse, SyntaxResponse, ComprehensiveAnalysisResponse
)

app = FastAPI(title="Caring API")


@app.get("/health")
def health():
    return {"status": "ok"}


# ==================== 데이터베이스 관리 API ====================

@app.post("/admin/db/migrate")
async def run_migration():
    """데이터베이스 마이그레이션 실행"""
    try:
        from alembic import command
        from alembic.config import Config
        
        print("🔄 마이그레이션 실행 중...")
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        
        return {
            "success": True,
            "message": "마이그레이션이 성공적으로 실행되었습니다."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"마이그레이션 실패: {str(e)}")


@app.post("/admin/db/init")
async def init_database():
    """데이터베이스 초기화 (테이블 생성)"""
    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        all_tables = set(Base.metadata.tables.keys())
        missing_tables = all_tables - set(existing_tables)
        
        if missing_tables:
            print(f"🔨 테이블 생성 중: {', '.join(missing_tables)}")
            table_order = ['user', 'voice', 'voice_content', 'voice_analyze', 'question', 'voice_question']
            
            for table_name in table_order:
                if table_name in missing_tables:
                    table = Base.metadata.tables[table_name]
                    table.create(bind=engine, checkfirst=True)
            
            other_tables = missing_tables - set(table_order)
            if other_tables:
                for table_name in other_tables:
                    table = Base.metadata.tables[table_name]
                    table.create(bind=engine, checkfirst=True)
            
            return {
                "success": True,
                "message": "테이블이 생성되었습니다.",
                "created_tables": list(missing_tables)
            }
        else:
            return {
                "success": True,
                "message": "모든 테이블이 이미 존재합니다."
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터베이스 초기화 실패: {str(e)}")


@app.get("/admin/db/status")
async def get_database_status():
    """데이터베이스 상태 확인"""
    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        all_tables = set(Base.metadata.tables.keys())
        missing_tables = all_tables - set(existing_tables)
        
        return {
            "success": True,
            "total_tables": len(all_tables),
            "existing_tables": existing_tables,
            "missing_tables": list(missing_tables),
            "is_sync": len(missing_tables) == 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"상태 확인 실패: {str(e)}")

# --------------------------------------auth API--------------------------------------

# POST : 회원가입
@app.post("/sign-up", response_model=SignupResponse)
async def sign_up(request: SignupRequest):
    """회원가입 API"""
    db = next(get_db())
    auth_service = get_auth_service(db)
    
    result = auth_service.signup(
        name=request.name,
        birthdate=request.birthdate,
        username=request.username,
        password=request.password,
        role=request.role,
        connecting_user_code=request.connecting_user_code
    )
    
    if result["success"]:
        return SignupResponse(
            message="회원가입이 완료되었습니다.",
            user_code=result["user_code"],
            username=result["username"],
            name=result["name"],
            role=result["role"]
        )
    else:
        raise HTTPException(status_code=400, detail=result["error"])


# POST : 로그인
@app.post("/sign-in", response_model=SigninResponse)
async def sign_in(request: SigninRequest, role: str):
    """로그인 API (role은 Request Parameter)"""
    db = next(get_db())
    auth_service = get_auth_service(db)
    
    result = auth_service.signin(
        username=request.username,
        password=request.password,
        role=role
    )
    
    if result["success"]:
        return SigninResponse(
            message="로그인 성공",
            username=result["username"],
            name=result["name"],
            role=result["role"]
        )
    else:
        raise HTTPException(status_code=401, detail=result["error"])


# POST : 사용자 음성 업로드
# @app.post("/users/voices", response_model=UserVoiceUploadResponse)
# async def upload_user_voice(
#     file: UploadFile = File(...),
#     username: str = Form(...)
# ):
#     """사용자 음성 파일 업로드 (S3 + DB 저장)"""
#     db = next(get_db())
#     voice_service = get_voice_service(db)
    
#     result = await voice_service.upload_user_voice(file, username)
    
#     if result["success"]:
#         return UserVoiceUploadResponse(
#             success=True,
#             message=result["message"],
#             voice_id=result.get("voice_id")
#         )
#     else:
#         raise HTTPException(status_code=400, detail=result["message"])


# --------------------------------------voice API--------------------------------------
# GET : 사용자 음성 리스트 조회
@app.get("/users/voices", response_model=UserVoiceListResponse)
async def get_user_voice_list(username: str):
    """사용자 음성 리스트 조회"""
    db = next(get_db())
    voice_service = get_voice_service(db)
    
    result = voice_service.get_user_voice_list(username)
    
    return UserVoiceListResponse(
        success=result["success"],
        voices=result.get("voices", [])
    )


# GET : 사용자 음성 상세 조회
@app.get("/users/voices/{voice_id}", response_model=UserVoiceDetailResponse)
async def get_user_voice_detail(voice_id: int, username: str):
    """voice_id와 username으로 상세 조회"""
    db = next(get_db())
    voice_service = get_voice_service(db)
    result = voice_service.get_user_voice_detail(voice_id, username)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Not Found"))
    return UserVoiceDetailResponse(
        voice_id=voice_id,
        title=result.get("title"),
        top_emotion=result.get("top_emotion"),
        created_at=result.get("created_at", ""),
        voice_content=result.get("voice_content"),
    )


# DELETE : 유저 특정 음성 삭제
@app.delete("/users/voices/{voice_id}")
async def delete_user_voice(voice_id: int, username: str):
    db = next(get_db())
    voice_service = get_voice_service(db)
    result = voice_service.delete_user_voice(voice_id, username)
    if result.get("success"):
        return {"success": True}
    raise HTTPException(status_code=400, detail=result.get("message", "Delete failed"))


# POST : 질문과 함께 음성 업로드
@app.post("/users/voices", response_model=VoiceQuestionUploadResponse)
async def upload_voice_with_question(
    file: UploadFile = File(...),
    question_id: int = Form(...),
    username: str = None,
):
    """질문과 함께 음성 파일 업로드 (S3 + DB 저장 + STT + voice_question 매핑)"""
    db = next(get_db())
    voice_service = get_voice_service(db)
    
    if not username:
        raise HTTPException(status_code=400, detail="username is required as query parameter")

    result = await voice_service.upload_voice_with_question(file, username, question_id)
    
    if result["success"]:
        return VoiceQuestionUploadResponse(
            success=True,
            message=result["message"],
            voice_id=result.get("voice_id"),
            question_id=result.get("question_id")
        )
    else:
        raise HTTPException(status_code=400, detail=result["message"])


# POST : upload voice with STT
@app.post("/voices/upload")
async def upload_voice(
    file: UploadFile = File(...),
    folder: Optional[str] = Form(default=None),
    language_code: str = Form(default="ko-KR")
):
    """음성 파일을 업로드하고 STT를 수행합니다."""
    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        raise HTTPException(status_code=500, detail="S3_BUCKET_NAME not configured")

    # 파일 내용을 메모리에 읽기 (두 번 사용하기 위해)
    file_content = await file.read()
    
    # S3 업로드
    base_prefix = VOICE_BASE_PREFIX.rstrip("/")
    effective_prefix = f"{base_prefix}/{folder or DEFAULT_UPLOAD_FOLDER}".rstrip("/")
    key = f"{effective_prefix}/{file.filename}"
    
    from io import BytesIO
    file_obj_for_s3 = BytesIO(file_content)
    upload_fileobj(bucket=bucket, key=key, fileobj=file_obj_for_s3)

    # STT 변환 - 파일 내용을 직접 사용
    from io import BytesIO
    temp_file_obj = BytesIO(file_content)
    
    # UploadFile과 유사한 객체 생성
    class TempUploadFile:
        def __init__(self, content, filename):
            self.file = content
            self.filename = filename
            self.content_type = "audio/wav"
    
    temp_upload_file = TempUploadFile(temp_file_obj, file.filename)
    stt_result = transcribe_voice(temp_upload_file, language_code)

    # 파일 목록 조회
    names = list_bucket_objects(bucket=bucket, prefix=effective_prefix)
    
    return {
        "uploaded": key,
        "files": names,
        "transcription": stt_result
    }


# GET : query my voice histories
@app.get("/voices")
async def list_voices(skip: int = 0, limit: int = 50, folder: Optional[str] = None):
    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        raise HTTPException(status_code=500, detail="S3_BUCKET_NAME not configured")
    base_prefix = VOICE_BASE_PREFIX.rstrip("/")
    effective_prefix = f"{base_prefix}/{folder or DEFAULT_UPLOAD_FOLDER}".rstrip("/")

    keys = list_bucket_objects(bucket=bucket, prefix=effective_prefix)
    # 페이징 비슷하게 slice만 적용
    sliced = keys[skip: skip + limit]
    return {"items": sliced, "count": len(sliced), "next": skip + len(sliced)}


# GET : query specific voice & show result
@app.get("/voices/{voice_id}")
async def get_voice(voice_id: str):
    # 내부 로직은 생략, 더미 상세 반환
    result = {
        "voice_id": voice_id,
        "filename": f"{voice_id}.wav",
        "status": "processed",
        "duration_sec": 12.34,
        "analysis": {"pitch_mean": 220.5, "energy": 0.82}
    }
    return JSONResponse(content=result)


# POST : analyze emotion from S3 file
@app.post("/voices/{voice_key}/analyze-emotion")
async def analyze_emotion_from_s3(voice_key: str):
    """S3에 저장된 음성 파일의 감정을 분석합니다."""
    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        raise HTTPException(status_code=500, detail="S3_BUCKET_NAME not configured")
    
    try:
        # S3에서 파일 다운로드
        from .s3_service import get_s3_client
        s3_client = get_s3_client()
        
        response = s3_client.get_object(Bucket=bucket, Key=voice_key)
        file_content = response['Body'].read()
        
        # BytesIO로 파일 객체 생성
        from io import BytesIO
        file_obj = BytesIO(file_content)
        
        # 파일명 추출 (키에서 마지막 부분)
        filename = voice_key.split('/')[-1]
        
        class FileWrapper:
            def __init__(self, content, filename, content_type):
                self.file = content
                self.filename = filename
                self.content_type = content_type
        
        emotion_file = FileWrapper(file_obj, filename, "audio/wav")
        emotion_result = analyze_voice_emotion(emotion_file)
        
        return {
            "voice_key": voice_key,
            "emotion_analysis": emotion_result
        }
        
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"파일을 찾을 수 없거나 분석 중 오류 발생: {str(e)}")


# POST : convert speech to text using Google STT
@app.post("/voices/transcribe")
async def transcribe_speech(
    file: UploadFile = File(...),
    language_code: str = "ko-KR"
):
    """음성 파일을 텍스트로 변환합니다."""
    stt_result = transcribe_voice(file, language_code)
    return stt_result


# POST : analyze text sentiment using Google NLP
@app.post("/nlp/sentiment")
async def analyze_sentiment(
    text: str,
    language_code: str = "ko"
):
    """텍스트의 감정을 분석합니다."""
    sentiment_result = analyze_text_sentiment(text, language_code)
    return sentiment_result


# POST : extract entities from text using Google NLP
@app.post("/nlp/entities")
async def extract_entities(
    text: str,
    language_code: str = "ko"
):
    """텍스트에서 엔티티를 추출합니다."""
    entities_result = analyze_text_entities(text, language_code)
    return entities_result


# POST : analyze text syntax using Google NLP
@app.post("/nlp/syntax")
async def analyze_syntax(
    text: str,
    language_code: str = "ko"
):
    """텍스트의 구문을 분석합니다."""
    syntax_result = analyze_text_syntax(text, language_code)
    return syntax_result


# POST : comprehensive text analysis using Google NLP
@app.post("/nlp/analyze")
async def analyze_text_comprehensive(
    text: str,
    language_code: str = "ko"
):
    """텍스트의 감정, 엔티티, 구문을 종합 분석합니다."""
    sentiment_result = analyze_text_sentiment(text, language_code)
    entities_result = analyze_text_entities(text, language_code)
    syntax_result = analyze_text_syntax(text, language_code)
    
    return {
        "text": text,
        "language_code": language_code,
        "sentiment_analysis": sentiment_result,
        "entity_analysis": entities_result,
        "syntax_analysis": syntax_result
    }
