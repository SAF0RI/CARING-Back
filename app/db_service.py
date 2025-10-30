from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, datetime
from .models import User, Voice, VoiceContent, VoiceAnalyze, Question, VoiceQuestion


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

    def get_user_by_user_code(self, user_code: str) -> Optional[User]:
        """user_code로 사용자 조회"""
        return self.db.query(User).filter(User.user_code == user_code).first()
    
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

    def get_voice_detail_for_username(self, voice_id: int, username: str) -> Optional[Voice]:
        """username으로 소유권을 검증하며 상세를 로드(joinedload)"""
        from sqlalchemy.orm import joinedload
        return (
            self.db.query(Voice)
            .join(User, Voice.user_id == User.user_id)
            .filter(Voice.voice_id == voice_id, User.username == username)
            .options(
                joinedload(Voice.questions),
                joinedload(Voice.voice_content),
                joinedload(Voice.voice_analyze),
            )
            .first()
        )
    
    def get_voice_by_key(self, voice_key: str) -> Optional[Voice]:
        """S3 키로 음성 파일 조회"""
        return self.db.query(Voice).filter(Voice.voice_key == voice_key).first()
    
    def get_voices_by_user(self, user_id: int, skip: int = 0, limit: int = 50) -> List[Voice]:
        """사용자별 음성 파일 목록 조회 (question 포함)"""
        from sqlalchemy.orm import joinedload
        return self.db.query(Voice).filter(Voice.user_id == user_id)\
            .options(joinedload(Voice.questions))\
            .order_by(Voice.created_at.desc()).offset(skip).limit(limit).all()

    def get_care_voices(self, care_username: str, skip: int = 0, limit: int = 20) -> List[Voice]:
        """보호자(care)의 연결 사용자 음성 중 voice_analyze가 존재하는 항목만 최신순 조회"""
        from sqlalchemy.orm import joinedload
        # 1) 보호자 조회
        care = self.get_user_by_username(care_username)
        if not care or not care.connecting_user_code:
            return []
        # 2) 연결된 사용자 조회
        linked_user = self.get_user_by_user_code(care.connecting_user_code)
        if not linked_user:
            return []
        # 3) 연결 사용자 음성 중 분석 완료만(join) 페이징
        q = (
            self.db.query(Voice)
            .join(VoiceAnalyze, VoiceAnalyze.voice_id == Voice.voice_id)
            .filter(Voice.user_id == linked_user.user_id)
            .options(joinedload(Voice.questions), joinedload(Voice.voice_analyze))
            .order_by(Voice.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return q.all()
    
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
                           neutral_bps: int, angry_bps: int, fear_bps: int, surprise_bps: int = 0,
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
            surprise_bps=surprise_bps,
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
                           neutral_bps: int, angry_bps: int, fear_bps: int, surprise_bps: Optional[int] = None,
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
            if surprise_bps is not None:
                voice_analyze.surprise_bps = surprise_bps
            if top_emotion is not None:
                voice_analyze.top_emotion = top_emotion
            if top_confidence_bps is not None:
                voice_analyze.top_confidence_bps = top_confidence_bps
            if model_version is not None:
                voice_analyze.model_version = model_version
            
            self.db.commit()
            self.db.refresh(voice_analyze)
        return voice_analyze
    
    # Question 관련 메서드
    def create_question(self, question_category: str, content: str) -> Question:
        """질문 템플릿 생성"""
        question = Question(
            question_category=question_category,
            content=content
        )
        self.db.add(question)
        self.db.commit()
        self.db.refresh(question)
        return question
    
    def get_questions_by_category(self, category: str) -> List[Question]:
        """카테고리별 질문 조회"""
        return self.db.query(Question).filter(Question.question_category == category).all()
    
    def get_all_questions(self) -> List[Question]:
        """전체 질문 조회"""
        return self.db.query(Question).all()
    
    def get_question_by_id(self, question_id: int) -> Optional[Question]:
        """ID로 질문 조회"""
        return self.db.query(Question).filter(Question.question_id == question_id).first()
    
    # VoiceQuestion 관련 메서드
    def link_voice_question(self, voice_id: int, question_id: int) -> VoiceQuestion:
        """Voice와 Question 연결"""
        voice_question = VoiceQuestion(
            voice_id=voice_id,
            question_id=question_id
        )
        self.db.add(voice_question)
        self.db.commit()
        self.db.refresh(voice_question)
        return voice_question
    
    def get_questions_by_voice_id(self, voice_id: int) -> List[Question]:
        """음성에 연결된 질문 조회"""
        return self.db.query(Question).join(VoiceQuestion).filter(VoiceQuestion.voice_id == voice_id).all()
    
    def get_voices_by_question_id(self, question_id: int) -> List[Voice]:
        """질문에 연결된 음성 조회"""
        return self.db.query(Voice).join(VoiceQuestion).filter(VoiceQuestion.question_id == question_id).all()
    
    def unlink_voice_question(self, voice_id: int, question_id: int) -> bool:
        """Voice와 Question 연결 해제"""
        voice_question = self.db.query(VoiceQuestion).filter(
            VoiceQuestion.voice_id == voice_id,
            VoiceQuestion.question_id == question_id
        ).first()
        if voice_question:
            self.db.delete(voice_question)
            self.db.commit()
            return True
        return False

    # 삭제 관련
    def get_voice_owned_by_username(self, voice_id: int, username: str) -> Optional[Voice]:
        """username 소유의 voice 조회"""
        return (
            self.db.query(Voice)
            .join(User, Voice.user_id == User.user_id)
            .filter(Voice.voice_id == voice_id, User.username == username)
            .first()
        )

    def delete_voice_with_relations(self, voice_id: int) -> bool:
        """연관 데이터(voice_question, voice_content, voice_analyze) 삭제 후 voice 삭제"""
        # voice_question
        self.db.query(VoiceQuestion).filter(VoiceQuestion.voice_id == voice_id).delete(synchronize_session=False)
        # voice_content
        self.db.query(VoiceContent).filter(VoiceContent.voice_id == voice_id).delete(synchronize_session=False)
        # voice_analyze
        self.db.query(VoiceAnalyze).filter(VoiceAnalyze.voice_id == voice_id).delete(synchronize_session=False)
        # voice
        deleted = self.db.query(Voice).filter(Voice.voice_id == voice_id).delete(synchronize_session=False)
        self.db.commit()
        return deleted > 0


def get_db_service(db: Session) -> DatabaseService:
    """데이터베이스 서비스 인스턴스 생성"""
    return DatabaseService(db)
