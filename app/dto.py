from pydantic import BaseModel
from typing import Optional
from datetime import date


# 회원가입 관련 DTO
class SignupRequest(BaseModel):
    name: str
    birthdate: str  # YYYY.MM.DD
    username: str
    password: str
    role: str  # USER or CARE
    connecting_user_code: Optional[str] = None  # CARE 역할일 때 연결할 사용자 코드


class SignupResponse(BaseModel):
    message: str
    user_code: str
    username: str
    name: str
    role: str


# 음성 관련 DTO
class VoiceUploadRequest(BaseModel):
    folder: Optional[str] = None
    language_code: str = "ko-KR"


class VoiceUploadResponse(BaseModel):
    uploaded: str
    files: list[str]
    transcription: dict


class VoiceListResponse(BaseModel):
    items: list[str]
    count: int
    next: int


class VoiceDetailResponse(BaseModel):
    voice_id: str
    filename: str
    status: str
    duration_sec: float
    analysis: dict


# 감정 분석 관련 DTO
class EmotionAnalysisResponse(BaseModel):
    voice_key: str
    emotion_analysis: dict


# STT 관련 DTO
class TranscribeRequest(BaseModel):
    language_code: str = "ko-KR"


class TranscribeResponse(BaseModel):
    transcript: str
    confidence: float
    language_code: str
    audio_duration: float
    sample_rate: int


# NLP 관련 DTO
class NLPAnalysisRequest(BaseModel):
    text: str
    language_code: str = "ko"


class SentimentResponse(BaseModel):
    sentiment: dict
    sentences: list[dict]
    language_code: str


class EntitiesResponse(BaseModel):
    entities: list[dict]
    language_code: str


class SyntaxResponse(BaseModel):
    tokens: list[dict]
    language_code: str


class ComprehensiveAnalysisResponse(BaseModel):
    text: str
    language_code: str
    sentiment_analysis: dict
    entity_analysis: dict
    syntax_analysis: dict


# 공통 응답 DTO
class ErrorResponse(BaseModel):
    detail: str


class SuccessResponse(BaseModel):
    message: str
    status: str = "success"
