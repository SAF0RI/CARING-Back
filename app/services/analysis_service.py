import os
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from ..models import Voice, VoiceComposite, User, WeeklyResult, FrequencyResult


def _get_openai_client():
    """OpenAI 클라이언트 생성 (env에서 키 로드)"""
    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not configured in environment")
    return OpenAI(api_key=api_key)


def _call_openai(messages: List[Dict[str, str]], model: Optional[str] = None) -> str:
    """Chat Completions 호출 래퍼"""
    client = _get_openai_client()
    use_model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    resp = client.chat.completions.create(
        model=use_model,
        messages=messages,
        temperature=0.7,
        max_tokens=400,
    )
    return (resp.choices[0].message.content or "").strip()


def _query_weekly_top_emotions(session: Session, user_id: int) -> Dict[str, List[str]]:
    """최근 7일간 날짜별 top_emotion 목록 조회 (YYYY-MM-DD -> [emotion,...])"""
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=6)
    q = (
        session.query(Voice, VoiceComposite)
        .join(VoiceComposite, Voice.voice_id == VoiceComposite.voice_id)
        .filter(
            Voice.user_id == user_id,
            Voice.created_at >= datetime.combine(start_dt.date(), datetime.min.time()),
            Voice.created_at <= datetime.combine(end_dt.date(), datetime.max.time()),
        )
        .order_by(Voice.created_at.asc())
    )
    by_day: Dict[str, List[str]] = defaultdict(list)
    for v, vc in q:
        day = v.created_at.date().strftime("%Y-%m-%d") if v.created_at else None
        if not day:
            continue
        em = (vc.top_emotion or "unknown") if vc else "unknown"
        by_day[day].append(em)
    return dict(by_day)


def _query_month_emotion_counts(session: Session, user_id: int) -> Dict[str, int]:
    """이번 달의 emotion 빈도수 (voice_composite.top_emotion 기준)"""
    now = datetime.now()
    start = datetime(now.year, now.month, 1)
    # 다음 달 1일
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1)
    else:
        next_month = datetime(now.year, now.month + 1, 1)

    q = (
        session.query(Voice, VoiceComposite)
        .join(VoiceComposite, Voice.voice_id == VoiceComposite.voice_id)
        .filter(
            Voice.user_id == user_id,
            Voice.created_at >= start,
            Voice.created_at < next_month,
        )
    )
    cnt = Counter()
    for v, vc in q:
        em = (vc.top_emotion or "unknown") if vc else "unknown"
        cnt[em] += 1
    return dict(cnt)


def _build_weekly_prompt(user_name: str, by_day: Dict[str, List[str]]) -> List[Dict[str, str]]:
    """주간 분석 프롬프트 구성"""
    lines = [f"대상 사용자: {user_name}"]
    if not by_day:
        lines.append("최근 7일 동안 감정 분석 데이터가 없습니다.")
    else:
        lines.append("최근 7일 간 날짜별 대표 감정 목록입니다.")
        for day in sorted(by_day.keys()):
            vals = ", ".join(by_day[day]) if by_day[day] else "(없음)"
            lines.append(f"- {day}: {vals}")
    system = {
        "role": "system",
        "content": (
            "너는 노년층 혹은 장애인 케어 서비스의 감정 코치다. 한국어로 공감적이고 간결하게, 1~3문장으로 "
            "주간 추세를 요약해라. 데이터가 없거나 매우 적은 경우에는 그 사실을 명확히 언급하고, "
            "추측하지 말고 관찰적인 표현만 사용해라. 과장 없이 관찰 중심으로 서술하고, 조언은 최소화한다."
        ),
    }
    user = {
        "role": "user",
        "content": (
            "다음 날짜별 감정 목록을 바탕으로 주간 감정 추세 한 문단(1~3문장)으로 요약해줘. "
            "데이터가 없으면 '최근 7일 동안 감정 분석 데이터가 없었습니다'처럼 명확히 알려줘.\n" + "\n".join(lines)
        ),
    }
    return [system, user]


def _build_frequency_prompt(user_name: str, counts: Dict[str, int]) -> List[Dict[str, str]]:
    """월간 빈도수 분석 프롬프트 구성"""
    items = ", ".join([f"{k}:{v}" for k, v in sorted(counts.items())]) if counts else "(데이터 없음)"
    system = {
        "role": "system",
        "content": (
            "너는 노년층 혹은 장애인 케어 서비스의 감정 코치다. 한국어로 공감적이고 간결하게, 1~3문장으로 "
            "월간 감정 빈도 특성을 요약해라. 데이터가 없거나 매우 적은 경우에는 그 사실을 명확히 언급하고, "
            "추측하지 말고 관찰적인 표현만 사용해라. 감정이 일부 확인되면 '일부 확인'처럼 신중한 표현을 사용해라."
        ),
    }
    user = {
        "role": "user",
        "content": (
            f"대상 사용자: {user_name}\n이 달의 대표 감정 빈도수는 다음과 같아: {items}. "
            "월간 감정 경향을 1~3문장으로 요약해줘. 데이터가 없으면 '이번 달에는 감정 분석 데이터가 없었습니다'처럼 명확히 알려줘."
        ),
    }
    return [system, user]


def get_weekly_result(session: Session, username: str, is_care: bool = False) -> str:
    """주간 종합분석 결과 메시지 생성"""
    from ..auth_service import get_auth_service
    auth = get_auth_service(session)
    owner = auth.get_user_by_username(username)
    if not owner:
        raise ValueError("user not found")

    # care인 경우 연결된 유저로 전환
    target_user = owner
    if is_care:
        if owner.role != 'CARE' or not owner.connecting_user_code:
            raise ValueError("invalid care user or not connected")
        target_user = auth.get_user_by_username(owner.connecting_user_code)
        if not target_user:
            raise ValueError("connected user not found")

    # 최신 voice_composite_id 조회
    latest_vc = (
        session.query(VoiceComposite.voice_composite_id)
        .join(Voice, Voice.voice_id == VoiceComposite.voice_id)
        .filter(Voice.user_id == target_user.user_id)
        .order_by(VoiceComposite.created_at.desc())
        .first()
    )
    latest_vc_id = latest_vc[0] if latest_vc else None

    # 캐시 조회
    cache = session.query(WeeklyResult).filter(WeeklyResult.user_id == target_user.user_id).first()
    if cache and cache.latest_voice_composite_id == latest_vc_id:
        return cache.message

    # 생성 후 캐시 저장/갱신
    by_day = _query_weekly_top_emotions(session, target_user.user_id)
    messages = _build_weekly_prompt(target_user.name, by_day)
    msg = _call_openai(messages)

    if cache:
        cache.message = msg
        cache.latest_voice_composite_id = latest_vc_id
    else:
        session.add(WeeklyResult(
            user_id=target_user.user_id,
            latest_voice_composite_id=latest_vc_id,
            message=msg,
        ))
    session.commit()
    return msg


def get_frequency_result(session: Session, username: str, is_care: bool = False) -> str:
    """월간 빈도 종합분석 결과 메시지 생성"""
    from ..auth_service import get_auth_service
    auth = get_auth_service(session)
    owner = auth.get_user_by_username(username)
    if not owner:
        raise ValueError("user not found")

    target_user = owner
    if is_care:
        if owner.role != 'CARE' or not owner.connecting_user_code:
            raise ValueError("invalid care user or not connected")
        target_user = auth.get_user_by_username(owner.connecting_user_code)
        if not target_user:
            raise ValueError("connected user not found")

    # 최신 voice_composite_id 조회
    latest_vc = (
        session.query(VoiceComposite.voice_composite_id)
        .join(Voice, Voice.voice_id == VoiceComposite.voice_id)
        .filter(Voice.user_id == target_user.user_id)
        .order_by(VoiceComposite.created_at.desc())
        .first()
    )
    latest_vc_id = latest_vc[0] if latest_vc else None

    # 캐시 조회
    cache = session.query(FrequencyResult).filter(FrequencyResult.user_id == target_user.user_id).first()
    if cache and cache.latest_voice_composite_id == latest_vc_id:
        return cache.message

    # 생성 후 캐시 저장/갱신
    counts = _query_month_emotion_counts(session, target_user.user_id)
    messages = _build_frequency_prompt(target_user.name, counts)
    msg = _call_openai(messages)

    if cache:
        cache.message = msg
        cache.latest_voice_composite_id = latest_vc_id
    else:
        session.add(FrequencyResult(
            user_id=target_user.user_id,
            latest_voice_composite_id=latest_vc_id,
            message=msg,
        ))
    session.commit()
    return msg


