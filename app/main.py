import os
from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, APIRouter, Depends
from fastapi.responses import JSONResponse
from typing import List
from datetime import datetime
from .s3_service import upload_fileobj, list_bucket_objects, list_bucket_objects_with_urls
from .constants import VOICE_BASE_PREFIX, DEFAULT_UPLOAD_FOLDER
from .emotion_service import analyze_voice_emotion
from .stt_service import transcribe_voice
from .nlp_service import analyze_text_sentiment, analyze_text_entities, analyze_text_syntax
from .database import create_tables, engine, get_db
from sqlalchemy.orm import Session
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
    VoiceAnalyzePreviewResponse,
    UserInfoResponse, CareInfoResponse,
    FcmTokenRegisterRequest, FcmTokenRegisterResponse, FcmTokenDeactivateResponse,
    NotificationListResponse,
    TopEmotionResponse, CareTopEmotionResponse,
    AnalysisResultResponse, WeeklyAnalysisCombinedResponse, FrequencyAnalysisCombinedResponse
)
from .care_service import CareService
import random
from .routers import composite_router
from .exceptions import (
    AppException, ValidationException, RuntimeException,
    DatabaseException, OutOfMemoryException, InternalServerException
)
from fastapi.exceptions import RequestValidationError
from pymysql import OperationalError as PyMysqlOperationalError
from sqlalchemy.exc import SQLAlchemyError
import traceback

app = FastAPI(title="Caring API")


# ============ 전역 예외 핸들러 ============
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """HTTPException 처리 - validation/runtime은 400, 기타는 그대로"""
    status_code = exc.status_code
    
    # validation 오류나 client 오류는 400으로 통일
    if status_code in (400, 401, 403, 404, 422):
        status_code = 400
    
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "error",
            "statusCode": status_code,
            "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    """FastAPI validation 오류 처리"""
    errors = exc.errors()
    message = "Validation error"
    if errors:
        first_error = errors[0]
        field = ".".join(str(loc) for loc in first_error.get("loc", []))
        msg = first_error.get("msg", "")
        message = f"{field}: {msg}" if field else msg
    
    return JSONResponse(
        status_code=400,
        content={
            "status": "error",
            "statusCode": 400,
            "message": message
        }
    )


@app.exception_handler(AppException)
async def app_exception_handler(request, exc: AppException):
    """커스텀 애플리케이션 예외 처리"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "statusCode": exc.status_code,
            "message": exc.message
        }
    )


@app.exception_handler(PyMysqlOperationalError)
async def mysql_exception_handler(request, exc: PyMysqlOperationalError):
    """MySQL 데이터베이스 오류 처리"""
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "statusCode": 500,
            "message": f"Database error: {str(exc)}"
        }
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request, exc: SQLAlchemyError):
    """SQLAlchemy 데이터베이스 오류 처리"""
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "statusCode": 500,
            "message": f"Database error: {str(exc)}"
        }
    )


@app.exception_handler(MemoryError)
async def memory_exception_handler(request, exc):
    """메모리 부족 오류 처리"""
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "statusCode": 500,
            "message": f"Out of memory: {str(exc)}"
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    """기타 모든 예외 처리"""
    # 예외 타입에 따라 status_code 결정
    exc_type = type(exc).__name__
    exc_message = str(exc)
    
    # 런타임/검증 오류로 보이는 경우 400
    if any(keyword in exc_type.lower() or keyword in exc_message.lower() 
           for keyword in ['validation', 'value', 'type', 'attribute', 'key']):
        status_code = 400
    else:
        # DB 오류나 기타는 500
        status_code = 500
    
    # 디버깅을 위한 로그 출력
    print(f"[Global Exception] {exc_type}: {exc_message}")
    print(traceback.format_exc())
    
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "error",
            "statusCode": status_code,
            "message": exc_message
        }
    )

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

@admin_router.get("/memory")
async def get_memory_status():
    """메모리 사용량 조회"""
    from .memory_monitor import get_memory_info
    return get_memory_info()

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
async def sign_up(request: SignupRequest, db: Session = Depends(get_db)):
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
async def sign_in(request: SigninRequest, role: str, db: Session = Depends(get_db)):
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


@app.post("/sign-out")
async def sign_out(username: str, db: Session = Depends(get_db)):
    """로그아웃 및 FCM 토큰 비활성화"""
    
    # 사용자 조회
    from .auth_service import get_auth_service
    auth_service = get_auth_service(db)
    user = auth_service.get_user_by_username(username)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # FCM 토큰 비활성화
    from .repositories.fcm_repo import deactivate_fcm_tokens_by_user
    deactivated_count = deactivate_fcm_tokens_by_user(db, user.user_id)
    
    return {
        "message": "로그아웃 완료",
        "deactivated_tokens": deactivated_count
    }

# ============== users 영역 (음성 업로드/조회/삭제 등) =============
def _verify_user_role(username: str, db: Session):
    """username이 USER 역할인지 검증"""
    auth_service = get_auth_service(db)
    user = auth_service.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != 'USER':
        raise HTTPException(status_code=403, detail="Only USER role can access this endpoint")
    return user

@users_router.get("", response_model=UserInfoResponse)
async def get_user_info(username: str, db: Session = Depends(get_db)):
    """일반 유저 내정보 조회 (이름, username, 연결된 보호자 이름)"""
    _verify_user_role(username, db)
    auth_service = get_auth_service(db)
    result = auth_service.get_user_info(username)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "조회 실패"))
    return UserInfoResponse(
        name=result["name"],
        username=result["username"],
        connected_care_name=result.get("connected_care_name")
    )

@users_router.get("/voices", response_model=UserVoiceListResponse)
async def get_user_voice_list(username: str, db: Session = Depends(get_db)):
    _verify_user_role(username, db)
    voice_service = get_voice_service(db)
    result = voice_service.get_user_voice_list(username)
    return UserVoiceListResponse(success=result["success"], voices=result.get("voices", []))

@users_router.get("/voices/{voice_id}", response_model=UserVoiceDetailResponse)
async def get_user_voice_detail(voice_id: int, username: str, db: Session = Depends(get_db)):
    _verify_user_role(username, db)
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
        s3_url=result.get("s3_url"),
    )

@users_router.delete("/voices/{voice_id}")
async def delete_user_voice(voice_id: int, username: str, db: Session = Depends(get_db)):
    _verify_user_role(username, db)
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
    db: Session = Depends(get_db)
):
    if not username:
        raise HTTPException(status_code=400, detail="username is required as query parameter")
    _verify_user_role(username, db)
    voice_service = get_voice_service(db)
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

@users_router.get("/voices/analyzing/frequency", response_model=FrequencyAnalysisCombinedResponse)
async def get_user_emotion_frequency(username: str, month: str, db: Session = Depends(get_db)):
    """사용자 본인의 월간 빈도 종합분석(OpenAI 캐시 + 기존 빈도 결과)"""
    _verify_user_role(username, db)
    from .services.analysis_service import get_frequency_result
    try:
        message = get_frequency_result(db, username=username, month=month, is_care=False)
        voice_service = get_voice_service(db)
        base = voice_service.get_user_emotion_monthly_frequency(username, month)
        frequency = base.get("frequency", {}) if base.get("success") else {}
        return FrequencyAnalysisCombinedResponse(message=message, frequency=frequency)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"분석 실패: {str(e)}")

@users_router.get("/voices/analyzing/weekly", response_model=WeeklyAnalysisCombinedResponse)
async def get_user_emotion_weekly(username: str, month: str, week: int, db: Session = Depends(get_db)):
    """사용자 본인의 주간 종합분석(OpenAI 캐시 사용)"""
    _verify_user_role(username, db)
    from .services.analysis_service import get_weekly_result
    try:
        message = get_weekly_result(db, username=username, month=month, week=week, is_care=False)
        # 기존 주간 요약도 함께 제공
        voice_service = get_voice_service(db)
        weekly_result = voice_service.get_user_emotion_weekly_summary(username, month, week)
        weekly = weekly_result.get("weekly", []) if weekly_result.get("success") else []
        return WeeklyAnalysisCombinedResponse(message=message, weekly=weekly)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"분석 실패: {str(e)}")


 


@users_router.get("/top_emotion", response_model=TopEmotionResponse)
async def get_user_top_emotion(username: str, db: Session = Depends(get_db)):
    """사용자 본인의 그날의 대표 emotion 조회 (서버 현재 날짜 기준)"""
    from .services.top_emotion_service import get_top_emotion_for_date
    
    # 사용자 검증 (USER 역할만 허용)
    user = _verify_user_role(username, db)
    
    # 서버 현재 날짜 사용
    today = datetime.now().date()
    date_str = today.strftime("%Y-%m-%d")
    
    # 그날의 대표 emotion 조회
    top_emotion = get_top_emotion_for_date(db, user.user_id, date_str)
    # fear -> anxiety 변환 (출력용)
    if top_emotion == "fear":
        top_emotion = "anxiety"
    
    return TopEmotionResponse(
        date=date_str,
        top_emotion=top_emotion
    )

@users_router.post("/fcm/register", response_model=FcmTokenRegisterResponse)
async def register_fcm_token(
    request: FcmTokenRegisterRequest,
    username: str,  # RequestParam
    db: Session = Depends(get_db)
):
    """FCM 토큰 등록 (로그인 후 호출)"""
    
    # 사용자 검증 (USER 역할만 허용)
    user = _verify_user_role(username, db)
    
    # FCM 토큰 등록
    from .repositories.fcm_repo import register_fcm_token
    try:
        token = register_fcm_token(
            session=db,
            user_id=user.user_id,
            fcm_token=request.fcm_token,
            device_id=request.device_id,
            platform=request.platform
        )
        
        return FcmTokenRegisterResponse(
            message="FCM 토큰이 등록되었습니다.",
            token_id=token.token_id,
            is_active=bool(token.is_active)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FCM 토큰 등록 실패: {str(e)}")


@users_router.post("/fcm/deactivate", response_model=FcmTokenDeactivateResponse)
async def deactivate_fcm_token(
    username: str,
    device_id: Optional[str] = None,  # 특정 기기만 비활성화 (없으면 전체)
    db: Session = Depends(get_db)
):
    """FCM 토큰 비활성화 (특정 기기 또는 전체)"""
    
    # 사용자 검증 (USER 역할만 허용)
    user = _verify_user_role(username, db)
    
    from .repositories.fcm_repo import deactivate_fcm_tokens_by_user, deactivate_fcm_token_by_device
    
    if device_id:
        # 특정 기기만 비활성화
        success = deactivate_fcm_token_by_device(db, user.user_id, device_id)
        count = 1 if success else 0
    else:
        # 전체 비활성화
        count = deactivate_fcm_tokens_by_user(db, user.user_id)
    
    return FcmTokenDeactivateResponse(
        message="FCM 토큰이 비활성화되었습니다.",
        deactivated_count=count
    )

# 모든 질문 목록 반환
@questions_router.get("")
async def get_questions(db: Session = Depends(get_db)):
    questions = db.query(Question).all()
    results = [
        {"question_id": q.question_id, "question_category": q.question_category, "content": q.content}
        for q in questions
    ]
    return {"success": True, "questions": results}

# 질문 랜덤 반환
@questions_router.get("/random")
async def get_random_question(db: Session = Depends(get_db)):
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
@care_router.get("", response_model=CareInfoResponse)
async def get_care_info(username: str, db: Session = Depends(get_db)):
    """보호자 내정보 조회 (이름, username, 연결된 피보호자 이름)"""
    auth_service = get_auth_service(db)
    result = auth_service.get_care_info(username)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "조회 실패"))
    return CareInfoResponse(
        name=result["name"],
        username=result["username"],
        connected_user_name=result.get("connected_user_name")
    )

@care_router.get("/users/voices", response_model=CareUserVoiceListResponse)
async def get_care_user_voice_list(
    care_username: str,
    date: Optional[str] = None,  # YYYY-MM-DD 형식, Optional
    db: Session = Depends(get_db)
):
    """보호자 페이지: 연결된 사용자의 분석 완료 음성 목록 조회
    
    - date: 날짜 필터 (YYYY-MM-DD). 없으면 전체 조회
    - pagination 제거됨
    """
    # 날짜 형식 검증 (있을 경우만)
    if date:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    voice_service = get_voice_service(db)
    result = voice_service.get_care_voice_list(care_username, date=date)
    return CareUserVoiceListResponse(success=result["success"], voices=result.get("voices", []))

@care_router.get("/users/voices/analyzing/frequency", response_model=FrequencyAnalysisCombinedResponse)
async def get_emotion_monthly_frequency(
    care_username: str, month: str, db: Session = Depends(get_db)
):
    """보호자: 연결 유저의 월간 빈도 종합분석(OpenAI 캐시 + 기존 빈도 결과)"""
    from .services.analysis_service import get_frequency_result
    try:
        message = get_frequency_result(db, username=care_username, month=month, is_care=True)
        from .care_service import CareService
        care_service = CareService(db)
        base = care_service.get_emotion_monthly_frequency(care_username, month)
        frequency = base.get("frequency", {}) if base.get("success") else {}
        return FrequencyAnalysisCombinedResponse(message=message, frequency=frequency)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"분석 실패: {str(e)}")


 


 

@care_router.get("/users/voices/analyzing/weekly", response_model=WeeklyAnalysisCombinedResponse)
async def get_emotion_weekly_summary(
    care_username: str,
    month: str,
    week: int,
    db: Session = Depends(get_db)
):
    """보호자: 연결 유저의 주간 종합분석(OpenAI 캐시 사용)"""
    from .services.analysis_service import get_weekly_result
    try:
        message = get_weekly_result(db, username=care_username, month=month, week=week, is_care=True)
        # 기존 주간 요약도 함께 제공
        care_service = CareService(db)
        weekly_result = care_service.get_emotion_weekly_summary(care_username, month, week)
        weekly = weekly_result.get("weekly", []) if weekly_result.get("success") else []
        return WeeklyAnalysisCombinedResponse(message=message, weekly=weekly)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"분석 실패: {str(e)}")


 

@care_router.get("/notifications", response_model=NotificationListResponse)
async def get_care_notifications(care_username: str, db: Session = Depends(get_db)):
    """보호자 페이지: 연결된 유저의 알림 목록 조회"""
    from .models import Notification, Voice, User
    
    # 보호자 검증 및 연결 유저 확인
    auth_service = get_auth_service(db)
    care_user = auth_service.get_user_by_username(care_username)
    if not care_user or care_user.role != 'CARE' or not care_user.connecting_user_code:
        raise HTTPException(status_code=400, detail="invalid care user or not connected")
    
    connected_user = auth_service.get_user_by_username(care_user.connecting_user_code)
    if not connected_user:
        raise HTTPException(status_code=400, detail="connected user not found")
    
    # 연결된 유저의 voice들의 notification 조회
    notifications = (
        db.query(Notification)
        .join(Voice, Notification.voice_id == Voice.voice_id)
        .filter(Voice.user_id == connected_user.user_id)
        .order_by(Notification.created_at.desc())
        .all()
    )
    
    notification_items = [
        {
            "notification_id": n.notification_id,
            "voice_id": n.voice_id,
            "name": n.name,
            "top_emotion": "anxiety" if n.top_emotion == "fear" else n.top_emotion,  # fear -> anxiety (출력용)
            "created_at": n.created_at.isoformat() if n.created_at else ""
        }
        for n in notifications
    ]
    
    return NotificationListResponse(notifications=notification_items)


@care_router.get("/top_emotion", response_model=CareTopEmotionResponse)
async def get_care_top_emotion(care_username: str, db: Session = Depends(get_db)):
    """보호자 페이지: 연결된 유저의 그날의 대표 emotion 조회 (서버 현재 날짜 기준)"""
    from .services.top_emotion_service import get_top_emotion_for_date
    
    # 보호자 검증 및 연결 유저 확인
    auth_service = get_auth_service(db)
    care_user = auth_service.get_user_by_username(care_username)
    if not care_user or care_user.role != 'CARE' or not care_user.connecting_user_code:
        raise HTTPException(status_code=400, detail="invalid care user or not connected")
    
    connected_user = auth_service.get_user_by_username(care_user.connecting_user_code)
    if not connected_user:
        raise HTTPException(status_code=400, detail="connected user not found")
    
    # 서버 현재 날짜 사용
    today = datetime.now().date()
    date_str = today.strftime("%Y-%m-%d")
    
    # 그날의 대표 emotion 조회
    top_emotion = get_top_emotion_for_date(db, connected_user.user_id, date_str)
    # fear -> anxiety 변환 (출력용)
    if top_emotion == "fear":
        top_emotion = "anxiety"
    
    return CareTopEmotionResponse(
        date=date_str,
        user_name=connected_user.name,
        top_emotion=top_emotion
    )


@care_router.get("/voices/{voice_id}/composite")
async def get_care_voice_composite(voice_id: int, care_username: str, db: Session = Depends(get_db)):
    """보호자 페이지: 특정 음성의 융합 지표 조회 (감정 퍼센트 포함)
    - care_username 검증: CARE 역할이며 연결된 user의 voice인지 확인
    """

    # 보호자 검증 및 연결 유저 확인
    auth_service = get_auth_service(db)
    care_user = auth_service.get_user_by_username(care_username)
    if not care_user or care_user.role != 'CARE' or not care_user.connecting_user_code:
        raise HTTPException(status_code=400, detail="invalid care user or not connected")
    connected_user = auth_service.get_user_by_username(care_user.connecting_user_code)
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
        "username": connected_user.username,  # 매칭된 유저의 username
        "name": connected_user.name,  # 매칭된 유저의 name
        "created_at": voice.created_at.isoformat() if voice.created_at else None,  # 음성 생성일시

        # *_bps fields are hidden per design
        "happy_pct": pct(row.happy_bps),
        "sad_pct": pct(row.sad_bps),
        "neutral_pct": pct(row.neutral_bps),
        "angry_pct": pct(row.angry_bps),
        "anxiety_pct": pct(row.fear_bps),  # fear -> anxiety (출력용)
        "surprise_pct": pct(row.surprise_bps),
        "top_emotion": "anxiety" if row.top_emotion == "fear" else row.top_emotion,  # fear -> anxiety
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
        # top_emotion에서 fear -> anxiety 변환
        if top_emotion == "fear":
            top_emotion = "anxiety"
        
        return VoiceAnalyzePreviewResponse(
            voice_id=None,
            happy_bps=happy,
            sad_bps=sad,
            neutral_bps=neutral,
            angry_bps=angry,
            anxiety_bps=fear,  # fear -> anxiety (출력용)
            surprise_bps=surprise,
            top_emotion=top_emotion,
            top_confidence_bps=top_conf_bps,
            model_version=result.get("model_version")
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"emotion analyze failed: {str(e)}")

@test_router.get("/s3-urls")
async def test_s3_urls(limit: int = 10, expires_in: int = 3600):
    """테스트: env prefix로 S3 presigned URL을 조회하고 샘플을 반환"""
    bucket = os.getenv("S3_BUCKET_NAME")
    print(f"[TEST] [S3] bucket={bucket}")
    if not bucket:
        raise HTTPException(status_code=500, detail="S3_BUCKET_NAME not configured")
    prefix_env = os.getenv("S3_LIST_PREFIX")
    if not prefix_env:
        base_prefix = VOICE_BASE_PREFIX.rstrip("/")
        prefix_env = f"{base_prefix}/{DEFAULT_UPLOAD_FOLDER}".rstrip("/")
    urls = list_bucket_objects_with_urls(bucket=bucket, prefix=prefix_env, expires_in=expires_in)
    items = list(urls.items())
    sample = dict(items[: max(0, min(limit, len(items)))])
    return {
        "success": True,
        "prefix": prefix_env,
        "count": len(urls),
        "sample": sample,
    }

@test_router.get("/memory")
async def test_memory():
    """테스트: 메모리 사용량 조회"""
    from .memory_monitor import get_memory_info, log_memory_info
    log_memory_info("test/memory endpoint")
    return get_memory_info()

@test_router.get("/error")
async def test_error(statusCode: int):
    """테스트: 전역 예외 핸들러 테스트용 API
    - statusCode: 400 또는 500을 받아서 해당 에러를 발생시킴
    """
    if statusCode == 400:
        # validation/runtime 오류 시뮬레이션
        raise HTTPException(status_code=400, detail="Test validation error: 잘못된 요청입니다.")
    elif statusCode == 500:
        # 내부 서버 오류 시뮬레이션
        from .exceptions import DatabaseException
        raise DatabaseException("Test database error: 데이터베이스 연결에 실패했습니다.")
    else:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid statusCode: {statusCode}. Only 400 or 500 are allowed."
        )


@test_router.post("/fcm/send")
async def test_fcm_send(
    token: Optional[str] = None,
    title: str = "Test Title",
    body: str = "Test Body",
    db: Session = Depends(get_db)
):
    """단일 토큰으로 FCM 테스트 전송 (SDK에서 발급받은 토큰 사용)"""
    if not token:
        raise HTTPException(status_code=400, detail="token is required")
    from .services.fcm_service import FcmService
    svc = FcmService(db)
    result = svc.send_notification_to_tokens([token], title, body)
    return {"success": True, "result": result}


@test_router.get("/voice/{voice_id}/fusion")
async def test_emotion_fusion(voice_id: int, db: Session = Depends(get_db)):
    """테스트: 새로운 감정 융합 알고리즘 계산 (Late Fusion 방식)
    
    새로운 계산식:
    1. 텍스트 감정 점수 정규화: score = (score_bps - 5000) / 5000, magnitude = magnitude_x1000 / 1000
    2. 텍스트 감정을 6개 감정으로 확장하는 가중치 계산
    3. Late Fusion: α * audio_score + β * text_score (α=0.7, β=0.3)
    4. top_emotion과 confidence 계산
    """
    from .repositories.voice_repo import get_audio_probs_by_voice_id, get_text_sentiment_by_voice_id
    from .models import VoiceAnalyze, VoiceContent
    
    # 1. 데이터 조회
    audio_probs = get_audio_probs_by_voice_id(db, voice_id)
    text_score_raw, text_magnitude_raw = get_text_sentiment_by_voice_id(db, voice_id)
    
    # VoiceAnalyze와 VoiceContent 원본 데이터 확인
    voice_analyze = db.query(VoiceAnalyze).filter(VoiceAnalyze.voice_id == voice_id).first()
    voice_content = db.query(VoiceContent).filter(VoiceContent.voice_id == voice_id).first()
    
    if not voice_analyze:
        raise HTTPException(status_code=404, detail=f"VoiceAnalyze not found for voice_id={voice_id}")
    if not voice_content:
        raise HTTPException(status_code=404, detail=f"VoiceContent not found for voice_id={voice_id}")
    
    # 2. 텍스트 감정 점수 정규화 (스케일 복구 규칙 적용)
    score_bps = voice_content.score_bps if voice_content.score_bps is not None else 5000
    magnitude_x1000 = voice_content.magnitude_x1000 if voice_content.magnitude_x1000 is not None else 0
    
    # 읽기 시: score = (score_bps / 10000) * 2 - 1  → [-1, 1]
    score = (float(score_bps) / 10000.0) * 2.0 - 1.0
    magnitude = float(magnitude_x1000) / 1000.0  # 원래 강도 단위 복원
    
    # Clamp score to [-1, 1]
    score = max(-1.0, min(1.0, score))
    magnitude = max(0.0, magnitude)
    
    # 3. 텍스트 감정을 6개 감정으로 확장하는 가중치 계산 (neutral 과대 비중 방지)
    pos = max(0.0, score)
    neg = max(0.0, -score)
    mag = max(0.0, min(1.0, magnitude))
    # 중립은 magnitude가 낮을 때만 비중 유지, 강도가 높을수록 감정으로 분배
    neutral_base = (1.0 - abs(score)) * (1.0 - mag)
    text_emotion_weight = {
        "happy": pos * mag,
        "sad": neg * mag,
        "neutral": max(0.0, neutral_base),
        "angry": neg * mag * 0.8,
        "fear": neg * mag * 0.7,
        "surprise": pos * mag * 0.8,
    }
    
    # 텍스트 가중치 정규화 (0~1 범위로)
    text_sum = sum(text_emotion_weight.values())
    if text_sum > 0:
        for k in text_emotion_weight:
            text_emotion_weight[k] = text_emotion_weight[k] / text_sum
    
    # 4. Late Fusion: α * audio_score + β * text_score (원래 비중)
    alpha = 0.7  # 오디오 비중
    beta = 0.3   # 텍스트 비중
    
    emotions = ["happy", "sad", "neutral", "angry", "fear", "surprise"]
    composite_score = {}
    
    for emotion in emotions:
        audio_score = audio_probs.get(emotion, 0.0)
        text_score = text_emotion_weight.get(emotion, 0.0)
        composite_score[emotion] = alpha * audio_score + beta * text_score
    
    # 5. 대표 감정 결정
    top_emotion = max(composite_score, key=composite_score.get)
    top_confidence = composite_score[top_emotion]
    top_confidence_bps = int(top_confidence * 10000)
    
    # 6. 감정별 수치를 bps로 변환
    emotion_bps = {emotion: int(score * 10000) for emotion, score in composite_score.items()}
    
    # fear -> anxiety 변환 (출력용)
    if top_emotion == "fear":
        top_emotion_display = "anxiety"
    else:
        top_emotion_display = top_emotion
    
    emotion_bps_display = {}
    for emotion, bps in emotion_bps.items():
        key = "anxiety" if emotion == "fear" else emotion
        emotion_bps_display[key] = bps
    
    return {
        "voice_id": voice_id,
        "input_data": {
            "audio": {
                "happy_bps": voice_analyze.happy_bps,
                "sad_bps": voice_analyze.sad_bps,
                "neutral_bps": voice_analyze.neutral_bps,
                "angry_bps": voice_analyze.angry_bps,
                "fear_bps": voice_analyze.fear_bps,
                "surprise_bps": voice_analyze.surprise_bps,
            },
            "text": {
                "score_bps": score_bps,
                "magnitude_x1000": magnitude_x1000,
                "score_normalized": score,
                "magnitude_normalized": magnitude,
            }
        },
        "intermediate": {
            "audio_probs": {k: round(v, 4) for k, v in audio_probs.items()},
            "text_emotion_weight": {k: round(v, 4) for k, v in text_emotion_weight.items()},
        },
        "fusion_params": {
            "alpha": alpha,
            "beta": beta,
        },
        "composite_score": {k: round(v, 4) for k, v in composite_score.items()},
        "result": {
            "top_emotion": top_emotion_display,
            "top_confidence_bps": top_confidence_bps,
            "emotion_bps": emotion_bps_display,
        }
    }

# ---------------- router 등록 ----------------
app.include_router(users_router)
app.include_router(care_router)
app.include_router(admin_router)
app.include_router(nlp_router)
app.include_router(test_router)
app.include_router(questions_router)
app.include_router(composite_router.router)
