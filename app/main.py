import os
from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, APIRouter
from fastapi.responses import JSONResponse
from typing import List
from .s3_service import upload_fileobj, list_bucket_objects
from .constants import VOICE_BASE_PREFIX, DEFAULT_UPLOAD_FOLDER
from .emotion_service import analyze_voice_emotion
from .stt_service import transcribe_voice
from .nlp_service import analyze_text_sentiment, analyze_text_entities, analyze_text_syntax
from .database import create_tables, engine, get_db
from .models import Base, Question, VoiceComposite
from .auth_service import get_auth_service
from .voice_service import get_voice_service
from .dto import (
    SignupRequest, SignupResponse,
    SigninRequest, SigninResponse,
    UserVoiceUploadRequest, UserVoiceUploadResponse,
    VoiceQuestionUploadResponse,
    UserVoiceListResponse, UserVoiceDetailResponse,
    CareUserVoiceListResponse,
    EmotionAnalysisResponse, TranscribeResponse,
    SentimentResponse, EntitiesResponse, SyntaxResponse, ComprehensiveAnalysisResponse,
    VoiceAnalyzePreviewResponse
)
from .care_service import CareService
import random
from .routers import composite_router

app = FastAPI(title="Caring API")

users_router = APIRouter(prefix="/users", tags=["users"])
care_router  = APIRouter(prefix="/care", tags=["care"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])
nlp_router   = APIRouter(prefix="/nlp", tags=["nlp"])
test_router  = APIRouter(prefix="/test", tags=["test"])
questions_router = APIRouter(prefix="/questions", tags=["questions"])

# Health
@app.get("/health")
def health():
    return {"status": "ok"}

# ============ Admin 영역 ============
@admin_router.post("/db/migrate")
async def run_migration():
    try:
        from alembic import command
        from alembic.config import Config
        print("🔄 마이그레이션 실행 중...")
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        return {"success": True, "message": "마이그레이션이 성공적으로 실행되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"마이그레이션 실패: {str(e)}")

@admin_router.post("/db/init")
async def init_database():
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
            return {"success": True, "message": "테이블이 생성되었습니다.", "created_tables": list(missing_tables)}
        else:
            return {"success": True, "message": "모든 테이블이 이미 존재합니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터베이스 초기화 실패: {str(e)}")

@admin_router.get("/db/status")
async def get_database_status():
    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        all_tables = set(Base.metadata.tables.keys())
        missing_tables = all_tables - set(existing_tables)
        return {"success": True, "total_tables": len(all_tables), "existing_tables": existing_tables, "missing_tables": list(missing_tables), "is_sync": len(missing_tables) == 0}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"상태 확인 실패: {str(e)}")

# ============ Auth 전용(signup, signin)은 루트에 남김 ===========
@app.post("/sign-up", response_model=SignupResponse)
async def sign_up(request: SignupRequest):
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

@app.post("/sign-in", response_model=SigninResponse)
async def sign_in(request: SigninRequest, role: str):
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

# ============== users 영역 (음성 업로드/조회/삭제 등) =============
@users_router.get("/voices", response_model=UserVoiceListResponse)
async def get_user_voice_list(username: str):
    db = next(get_db())
    voice_service = get_voice_service(db)
    result = voice_service.get_user_voice_list(username)
    return UserVoiceListResponse(success=result["success"], voices=result.get("voices", []))

@users_router.get("/voices/{voice_id}", response_model=UserVoiceDetailResponse)
async def get_user_voice_detail(voice_id: int, username: str):
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

@users_router.delete("/voices/{voice_id}")
async def delete_user_voice(voice_id: int, username: str):
    db = next(get_db())
    voice_service = get_voice_service(db)
    result = voice_service.delete_user_voice(voice_id, username)
    if result.get("success"):
        return {"success": True}
    raise HTTPException(status_code=400, detail=result.get("message", "Delete failed"))

@users_router.post("/voices", response_model=VoiceQuestionUploadResponse)
async def upload_voice_with_question(
    file: UploadFile = File(...),
    question_id: int = Form(...),
    username: str = None,
):
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

# 모든 질문 목록 반환
@questions_router.get("")
async def get_questions():
    db = next(get_db())
    questions = db.query(Question).all()
    results = [
        {"question_id": q.question_id, "question_category": q.question_category, "content": q.content}
        for q in questions
    ]
    return {"success": True, "questions": results}

# 질문 랜덤 반환
@questions_router.get("/random")
async def get_random_question():
    db = next(get_db())
    question_count = db.query(Question).count()
    if question_count == 0:
        return {"success": False, "question": None}
    import random
    offset = random.randint(0, question_count - 1)
    q = db.query(Question).offset(offset).first()
    if q:
        result = {"question_id": q.question_id, "question_category": q.question_category, "content": q.content}
        return {"success": True, "question": result}
    return {"success": False, "question": None}

# ============== care 영역 (보호자전용) =============
@care_router.get("/users/voices", response_model=CareUserVoiceListResponse)
async def get_care_user_voice_list(care_username: str, skip: int = 0, limit: int = 20):
    db = next(get_db())
    voice_service = get_voice_service(db)
    result = voice_service.get_care_voice_list(care_username, skip=skip, limit=limit)
    return CareUserVoiceListResponse(success=result["success"], voices=result.get("voices", []))

@care_router.get("/users/voices/analyzing/frequency")
async def get_emotion_monthly_frequency(
    care_username: str, month: str
):
    """
    보호자 페이지: 연결된 유저의 한달간 감정 빈도수 집계 (CareService 내부 로직 사용)
    """
    db = next(get_db())
    care_service = CareService(db)
    return care_service.get_emotion_monthly_frequency(care_username, month)

@care_router.get("/users/voices/analyzing/weekly")
async def get_emotion_weekly_summary(
    care_username: str,
    month: str,
    week: int
):
    """보호자페이지 - 연결유저 월/주차별 요일 top 감정 통계"""
    db = next(get_db())
    care_service = CareService(db)
    return care_service.get_emotion_weekly_summary(care_username, month, week)

@care_router.get("/voices/{voice_id}/composite")
async def get_care_voice_composite(voice_id: int, care_username: str):
    """보호자 페이지: 특정 음성의 융합 지표 조회 (감정 퍼센트 포함)
    - care_username 검증: CARE 역할이며 연결된 user의 voice인지 확인
    """
    db = next(get_db())

    # 보호자 검증 및 연결 유저 확인
    auth_service = get_auth_service(db)
    care_user = auth_service.get_user_by_username(care_username)
    if not care_user or care_user.role != 'CARE' or not care_user.connecting_user_code:
        raise HTTPException(status_code=400, detail="invalid care user or not connected")
    connected_user = auth_service.get_user_by_code(care_user.connecting_user_code)
    if not connected_user:
        raise HTTPException(status_code=400, detail="connected user not found")

    # voice 소유권 검증
    from .models import Voice
    voice = db.query(Voice).filter(Voice.voice_id == voice_id).first()
    if not voice or voice.user_id != connected_user.user_id:
        raise HTTPException(status_code=403, detail="forbidden: not owned by connected user")

    row = db.query(VoiceComposite).filter(VoiceComposite.voice_id == voice_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="not found")

    def pct(bps: int | None) -> int:
        return int(round((bps or 0) / 100))

    return {
        "voice_id": voice_id,
        "valence_x1000": row.valence_x1000,
        "arousal_x1000": row.arousal_x1000,
        "intensity_x1000": row.intensity_x1000,
        "alpha_bps": row.alpha_bps or 0,
        "beta_bps": row.beta_bps or 0,
        # *_bps fields are hidden per design
        "happy_pct": pct(row.happy_bps),
        "sad_pct": pct(row.sad_bps),
        "neutral_pct": pct(row.neutral_bps),
        "angry_pct": pct(row.angry_bps),
        "fear_pct": pct(row.fear_bps),
        "surprise_pct": pct(row.surprise_bps),
        "top_emotion": row.top_emotion,
        "top_emotion_confidence_bps": row.top_emotion_confidence_bps or 0,
        "top_emotion_confidence_pct": pct(row.top_emotion_confidence_bps or 0),
    }

# ============== nlp 영역 (구글 NLP) =============
@nlp_router.post("/sentiment")
async def analyze_sentiment(text: str, language_code: str = "ko"):
    sentiment_result = analyze_text_sentiment(text, language_code)
    return sentiment_result

@nlp_router.post("/entities")
async def extract_entities(text: str, language_code: str = "ko"):
    entities_result = analyze_text_entities(text, language_code)
    return entities_result

@nlp_router.post("/syntax")
async def analyze_syntax(text: str, language_code: str = "ko"):
    syntax_result = analyze_text_syntax(text, language_code)
    return syntax_result

@nlp_router.post("/analyze")
async def analyze_text_comprehensive(text: str, language_code: str = "ko"):
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

# ============== test 영역 =============
@test_router.post("/voice/analyze", response_model=VoiceAnalyzePreviewResponse)
async def test_emotion_analyze(file: UploadFile = File(...)):
    try:
        data = await file.read()
        from io import BytesIO
        class FileWrapper:
            def __init__(self, content, filename):
                self.file = content
                self.filename = filename
                self.content_type = "audio/m4a" if filename.lower().endswith(".m4a") else "audio/wav"
        wrapped = FileWrapper(BytesIO(data), file.filename)
        result = analyze_voice_emotion(wrapped)
        probs = result.get("emotion_scores") or {}
        def to_bps(x):
            try:
                return max(0, min(10000, int(round(float(x) * 10000))))
            except Exception:
                return 0
        happy = to_bps(probs.get("happy", 0))
        sad = to_bps(probs.get("sad", 0))
        neutral = to_bps(probs.get("neutral", 0))
        angry = to_bps(probs.get("angry", 0))
        fear = to_bps(probs.get("fear", 0))
        surprise = to_bps(probs.get("surprise", 0))
        total = happy + sad + neutral + angry + fear + surprise
        if total == 0:
            neutral = 10000
            happy = sad = angry = fear = surprise = 0
        else:
            scale = 10000 / float(total)
            vals = {
                "happy": int(round(happy * scale)),
                "sad": int(round(sad * scale)),
                "neutral": int(round(neutral * scale)),
                "angry": int(round(angry * scale)),
                "fear": int(round(fear * scale)),
                "surprise": int(round(surprise * scale)),
            }
            diff = 10000 - sum(vals.values())
            if diff != 0:
                k = max(vals, key=lambda k: vals[k])
                vals[k] = max(0, min(10000, vals[k] + diff))
            happy, sad, neutral, angry, fear, surprise = (
                vals["happy"], vals["sad"], vals["neutral"], vals["angry"], vals["fear"], vals["surprise"]
            )
        top_emotion = result.get("top_emotion") or result.get("label") or result.get("emotion")
        top_conf_bps = to_bps(result.get("top_confidence") or result.get("confidence", 0))
        return VoiceAnalyzePreviewResponse(
            voice_id=None,
            happy_bps=happy,
            sad_bps=sad,
            neutral_bps=neutral,
            angry_bps=angry,
            fear_bps=fear,
            surprise_bps=surprise,
            top_emotion=top_emotion,
            top_confidence_bps=top_conf_bps,
            model_version=result.get("model_version")
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"emotion analyze failed: {str(e)}")

# ---------------- router 등록 ----------------
app.include_router(users_router)
app.include_router(care_router)
app.include_router(admin_router)
app.include_router(nlp_router)
app.include_router(test_router)
app.include_router(questions_router)
app.include_router(composite_router.router)
