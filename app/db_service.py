from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, datetime
from .models import User, Voice, VoiceContent, VoiceAnalyze


class DatabaseService:
    """데이터베이스 작업을 위한 서비스 클래스"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # User 관련 메서드
    def create_user(self, username: str, password: str, role: str, name: str, birthdate: date) -> User:
        """사용자 생성"""
        user = User(
            username=username,
            password=password,
            role=role,
            name=name,
            birthdate=birthdate
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """ID로 사용자 조회"""
        return self.db.query(User).filter(User.user_id == user_id).first()
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """사용자명으로 사용자 조회"""
        return self.db.query(User).filter(User.username == username).first()
    
    def get_users(self, skip: int = 0, limit: int = 100) -> List[User]:
        """사용자 목록 조회"""
        return self.db.query(User).offset(skip).limit(limit).all()
    
    # Voice 관련 메서드
    def create_voice(self, voice_key: str, voice_name: str, duration_ms: int, 
                    user_id: int, sample_rate: Optional[int] = None, 
                    bit_rate: Optional[int] = None) -> Voice:
        """음성 파일 메타데이터 생성"""
        voice = Voice(
            voice_key=voice_key,
            voice_name=voice_name,
            duration_ms=duration_ms,
            sample_rate=sample_rate,
            bit_rate=bit_rate,
            user_id=user_id
        )
        self.db.add(voice)
        self.db.commit()
        self.db.refresh(voice)
        return voice
    
    def get_voice_by_id(self, voice_id: int) -> Optional[Voice]:
        """ID로 음성 파일 조회"""
        return self.db.query(Voice).filter(Voice.voice_id == voice_id).first()
    
    def get_voice_by_key(self, voice_key: str) -> Optional[Voice]:
        """S3 키로 음성 파일 조회"""
        return self.db.query(Voice).filter(Voice.voice_key == voice_key).first()
    
    def get_voices_by_user(self, user_id: int, skip: int = 0, limit: int = 50) -> List[Voice]:
        """사용자별 음성 파일 목록 조회"""
        return self.db.query(Voice).filter(Voice.user_id == user_id)\
            .order_by(Voice.created_at.desc()).offset(skip).limit(limit).all()
    
    def get_all_voices(self, skip: int = 0, limit: int = 50) -> List[Voice]:
        """전체 음성 파일 목록 조회"""
        return self.db.query(Voice).order_by(Voice.created_at.desc()).offset(skip).limit(limit).all()
    
    # VoiceContent 관련 메서드
    def create_voice_content(self, voice_id: int, content: str, 
                           score_bps: Optional[int] = None, magnitude_x1000: Optional[int] = None,
                           locale: Optional[str] = None, provider: Optional[str] = None,
                           model_version: Optional[str] = None, confidence_bps: Optional[int] = None) -> VoiceContent:
        """음성 전사 및 텍스트 감정 분석 데이터 생성"""
        voice_content = VoiceContent(
            voice_id=voice_id,
            content=content,
            score_bps=score_bps,
            magnitude_x1000=magnitude_x1000,
            locale=locale,
            provider=provider,
            model_version=model_version,
            confidence_bps=confidence_bps
        )
        self.db.add(voice_content)
        self.db.commit()
        self.db.refresh(voice_content)
        return voice_content
    
    def get_voice_content_by_voice_id(self, voice_id: int) -> Optional[VoiceContent]:
        """음성 파일 ID로 전사 내용 조회"""
        return self.db.query(VoiceContent).filter(VoiceContent.voice_id == voice_id).first()
    
    def update_voice_content(self, voice_id: int, content: str, 
                           score_bps: Optional[int] = None, magnitude_x1000: Optional[int] = None,
                           locale: Optional[str] = None, provider: Optional[str] = None,
                           model_version: Optional[str] = None, confidence_bps: Optional[int] = None) -> Optional[VoiceContent]:
        """음성 전사 내용 업데이트"""
        voice_content = self.get_voice_content_by_voice_id(voice_id)
        if voice_content:
            voice_content.content = content
            if score_bps is not None:
                voice_content.score_bps = score_bps
            if magnitude_x1000 is not None:
                voice_content.magnitude_x1000 = magnitude_x1000
            if locale is not None:
                voice_content.locale = locale
            if provider is not None:
                voice_content.provider = provider
            if model_version is not None:
                voice_content.model_version = model_version
            if confidence_bps is not None:
                voice_content.confidence_bps = confidence_bps
            
            self.db.commit()
            self.db.refresh(voice_content)
        return voice_content
    
    # VoiceAnalyze 관련 메서드
    def create_voice_analyze(self, voice_id: int, happy_bps: int, sad_bps: int, 
                           neutral_bps: int, angry_bps: int, fear_bps: int,
                           top_emotion: Optional[str] = None, top_confidence_bps: Optional[int] = None,
                           model_version: Optional[str] = None) -> VoiceAnalyze:
        """음성 감정 분석 데이터 생성"""
        voice_analyze = VoiceAnalyze(
            voice_id=voice_id,
            happy_bps=happy_bps,
            sad_bps=sad_bps,
            neutral_bps=neutral_bps,
            angry_bps=angry_bps,
            fear_bps=fear_bps,
            top_emotion=top_emotion,
            top_confidence_bps=top_confidence_bps,
            model_version=model_version
        )
        self.db.add(voice_analyze)
        self.db.commit()
        self.db.refresh(voice_analyze)
        return voice_analyze
    
    def get_voice_analyze_by_voice_id(self, voice_id: int) -> Optional[VoiceAnalyze]:
        """음성 파일 ID로 감정 분석 결과 조회"""
        return self.db.query(VoiceAnalyze).filter(VoiceAnalyze.voice_id == voice_id).first()
    
    def update_voice_analyze(self, voice_id: int, happy_bps: int, sad_bps: int, 
                           neutral_bps: int, angry_bps: int, fear_bps: int,
                           top_emotion: Optional[str] = None, top_confidence_bps: Optional[int] = None,
                           model_version: Optional[str] = None) -> Optional[VoiceAnalyze]:
        """음성 감정 분석 결과 업데이트"""
        voice_analyze = self.get_voice_analyze_by_voice_id(voice_id)
        if voice_analyze:
            voice_analyze.happy_bps = happy_bps
            voice_analyze.sad_bps = sad_bps
            voice_analyze.neutral_bps = neutral_bps
            voice_analyze.angry_bps = angry_bps
            voice_analyze.fear_bps = fear_bps
            if top_emotion is not None:
                voice_analyze.top_emotion = top_emotion
            if top_confidence_bps is not None:
                voice_analyze.top_confidence_bps = top_confidence_bps
            if model_version is not None:
                voice_analyze.model_version = model_version
            
            self.db.commit()
            self.db.refresh(voice_analyze)
        return voice_analyze


# 편의 함수들
def get_db_service(db: Session) -> DatabaseService:
    """데이터베이스 서비스 인스턴스 생성"""
    return DatabaseService(db)
