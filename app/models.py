from sqlalchemy import Column, BigInteger, String, Date, DateTime, Integer, SmallInteger, Text, ForeignKey, CheckConstraint, UniqueConstraint, Index
from sqlalchemy.dialects.mysql import VARCHAR
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    """사용자 테이블"""
    __tablename__ = "user"
    
    user_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_code = Column(String(20), nullable=False, unique=True)  # 자동 생성되는 사용자 코드
    username = Column(String(64), nullable=False, unique=True)
    password = Column(String(72), nullable=False)  # bcrypt 해시
    role = Column(String(20), nullable=False)
    name = Column(String(50), nullable=False)
    birthdate = Column(Date, nullable=False)
    connecting_user_code = Column(String(20), nullable=True)  # CARE 역할일 때 연결할 사용자 코드
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    # 관계 설정
    voices = relationship("Voice", back_populates="user", cascade="all, delete-orphan")
    
    # 제약 조건
    __table_args__ = (
        CheckConstraint("role IN ('USER','CARE')", name='check_user_role'),
    )


class Voice(Base):
    """음성 파일 메타데이터 테이블"""
    __tablename__ = "voice"
    
    voice_id = Column(BigInteger, primary_key=True, autoincrement=True)
    voice_key = Column(String(1024), nullable=False)  # S3 key
    voice_name = Column(String(255), nullable=False)  # 제목
    duration_ms = Column(Integer, nullable=False)  # 길이(ms)
    sample_rate = Column(Integer, nullable=True)  # Hz
    bit_rate = Column(Integer, nullable=True)  # bps
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    user_id = Column(BigInteger, ForeignKey("user.user_id", ondelete="CASCADE"), nullable=False)
    
    # 관계 설정
    user = relationship("User", back_populates="voices")
    voice_content = relationship("VoiceContent", back_populates="voice", uselist=False, cascade="all, delete-orphan")
    voice_analyze = relationship("VoiceAnalyze", back_populates="voice", uselist=False, cascade="all, delete-orphan")
    questions = relationship("Question", secondary="voice_question", back_populates="voices")
    
    # 인덱스
    __table_args__ = (
        Index('idx_voice_user_created', 'user_id', 'created_at'),
        # voice_key의 일부(255자)만 인덱싱하여 길이 제한 문제 해결
        Index('idx_voice_key', 'voice_key', mysql_length=255),
    )


class VoiceContent(Base):
    """음성 전사 및 텍스트 감정 분석 테이블"""
    __tablename__ = "voice_content"
    
    voice_content_id = Column(BigInteger, primary_key=True, autoincrement=True)
    voice_id = Column(BigInteger, ForeignKey("voice.voice_id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)  # 전사 내용
    score_bps = Column(SmallInteger, nullable=True)  # -10000~10000 (감정 점수 * 10000)
    magnitude_x1000 = Column(Integer, nullable=True)  # 0~? (감정 강도 * 1000)
    locale = Column(String(10), nullable=True)  # 'ko-KR' 등
    provider = Column(String(32), nullable=True)  # 'google', 'aws' 등
    model_version = Column(String(32), nullable=True)
    confidence_bps = Column(SmallInteger, nullable=True)  # 0~10000 (신뢰도 * 10000)
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    
    # 관계 설정
    voice = relationship("Voice", back_populates="voice_content")
    
    # 제약 조건
    __table_args__ = (
        UniqueConstraint('voice_id', name='uq_vc_voice'),  # 1:1 관계
    )


class VoiceAnalyze(Base):
    """음성 감정 분석 테이블"""
    __tablename__ = "voice_analyze"
    
    voice_analyze_id = Column(BigInteger, primary_key=True, autoincrement=True)
    voice_id = Column(BigInteger, ForeignKey("voice.voice_id", ondelete="CASCADE"), nullable=False)
    happy_bps = Column(SmallInteger, nullable=False)  # 0~10000
    sad_bps = Column(SmallInteger, nullable=False)  # 0~10000
    neutral_bps = Column(SmallInteger, nullable=False)  # 0~10000
    angry_bps = Column(SmallInteger, nullable=False)  # 0~10000
    fear_bps = Column(SmallInteger, nullable=False)  # 0~10000
    top_emotion = Column(String(16), nullable=True)  # 'neutral' 등
    top_confidence_bps = Column(SmallInteger, nullable=True)  # 0~10000
    model_version = Column(String(32), nullable=True)
    analyzed_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    
    # 관계 설정
    voice = relationship("Voice", back_populates="voice_analyze")
    
    # 제약 조건
    __table_args__ = (
        UniqueConstraint('voice_id', name='uq_va_voice'),
        CheckConstraint("happy_bps <= 10000 AND sad_bps <= 10000 AND neutral_bps <= 10000 AND angry_bps <= 10000 AND fear_bps <= 10000", name='check_emotion_bps_range'),
        CheckConstraint("happy_bps + sad_bps + neutral_bps + angry_bps + fear_bps = 10000", name='check_emotion_bps_sum'),
    )


class Question(Base):
    """질문 템플릿 테이블"""
    __tablename__ = "question"
    
    question_id = Column(BigInteger, primary_key=True, autoincrement=True)
    question_category = Column(String(50), nullable=False)  # emotion, stress, physical, social, self_reflection
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    
    # 다대다 관계
    voices = relationship("Voice", secondary="voice_question", back_populates="questions")
    
    # 제약 조건
    __table_args__ = (
        CheckConstraint("question_category IN ('emotion', 'stress', 'physical', 'social', 'self_reflection')", name='check_question_category'),
    )


class VoiceQuestion(Base):
    """Voice와 Question의 다대다 매핑 테이블"""
    __tablename__ = "voice_question"
    
    voice_question_id = Column(BigInteger, primary_key=True, autoincrement=True)
    voice_id = Column(BigInteger, ForeignKey("voice.voice_id", ondelete="CASCADE"), nullable=False)
    question_id = Column(BigInteger, ForeignKey("question.question_id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    
    # 제약 조건
    __table_args__ = (
        UniqueConstraint('voice_id', 'question_id', name='uq_voice_question'),
    )
