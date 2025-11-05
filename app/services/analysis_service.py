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


def _query_weekly_top_emotions(session: Session, user_id: int, month: str, week: int) -> Dict[str, List[str]]:
    """특정 주차의 날짜별 대표 감정 1개로 집계 (YYYY-MM-DD -> [top_emotion])
    - 데이터 소스: voice_composite.top_emotion (fear는 anxiety로 매핑)
    - Unknown 제외 가능한 경우 제외 후 최빈값/동률-선출 로직 적용
    """
    from calendar import monthrange
    try:
        y, m = map(int, month.split("-"))
    except Exception:
        raise ValueError("month format YYYY-MM required")
    start_day = (week-1)*7+1
    end_day = min(week*7, monthrange(y, m)[1])
    start_date = datetime(y, m, start_day)
    end_date = datetime(y, m, end_day, 23, 59, 59)
    q = (
        session.query(Voice, VoiceComposite)
        .join(VoiceComposite, Voice.voice_id == VoiceComposite.voice_id)
        .filter(
            Voice.user_id == user_id,
            Voice.created_at >= start_date,
            Voice.created_at <= end_date,
        )
        .order_by(Voice.created_at.asc())
    )
    def _map_emotion(e: Optional[str]) -> str:
        if not e:
            return "unknown"
        try:
            return "anxiety" if str(e).lower() == "fear" else str(e)
        except Exception:
            return str(e)
    # 원시 수집(해당 날짜의 모든 항목)
    raw_by_day: Dict[str, List[str]] = defaultdict(list)
    for v, vc in q:
        day = v.created_at.date().strftime("%Y-%m-%d") if v.created_at else None
        if not day:
            continue
        em = (vc.top_emotion or "unknown") if vc else "unknown"
        raw_by_day[day].append(_map_emotion(em))
    # 날짜별 대표 감정 1개 산출
    from collections import Counter
    by_day_top: Dict[str, List[str]] = {}
    for day in sorted(raw_by_day.keys()):
        values = raw_by_day[day]
        non_unknown = [e for e in values if e and str(e).lower() not in ("unknown", "null", "none")]
        if non_unknown:
            cnt = Counter(non_unknown)
            top, top_count = cnt.most_common(1)[0]
            ties = {e for e, c in cnt.items() if c == top_count}
            if len(ties) > 1:
                for e in values:
                    if e in ties:
                        top = e
                        break
        else:
            top = values[0] if values else "unknown"
        by_day_top[day] = [top]
    return by_day_top


def _query_month_emotion_counts(session: Session, user_id: int, month: str) -> Dict[str, int]:
    """특정 월의 emotion 빈도수 (voice_composite.top_emotion 기준)"""
    try:
        y, m = map(int, month.split("-"))
    except Exception:
        raise ValueError("month format YYYY-MM required")
    start = datetime(y, m, 1)
    # 다음 달 1일
    if m == 12:
        next_month = datetime(y + 1, 1, 1)
    else:
        next_month = datetime(y, m + 1, 1)

    q = (
        session.query(Voice, VoiceComposite)
        .join(VoiceComposite, Voice.voice_id == VoiceComposite.voice_id)
        .filter(
            Voice.user_id == user_id,
            Voice.created_at >= start,
            Voice.created_at < next_month,
        )
    )
    def _map_emotion(e: Optional[str]) -> str:
        if not e:
            return "unknown"
        try:
            return "anxiety" if str(e).lower() == "fear" else str(e)
        except Exception:
            return str(e)

    cnt = Counter()
    for v, vc in q:
        em = (vc.top_emotion or "unknown") if vc else "unknown"
        cnt[_map_emotion(em)] += 1
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
            "너는 노년층 혹은 장애인 케어 서비스의 감정 코치다. 한국어로 공감적이고 자연스럽게, 1~3문장으로 "
            "주간 감정 추세를 반드시 요약해라. 데이터가 적어도 관찰 가능한 내용을 바탕으로 요약을 제공해야 한다. "
            "추측하지 말고 관찰적인 표현만 사용하고, 과장 없이 사실 중심으로 서술해라. "
            "조언은 최소화하고 관찰 결과에 집중해라. 또한 early/mid/late(초반/중반/후반) 시기를 구분하여 감정 흐름이 바뀌는 지점을 틀림없이 분석하여라. "
            "감정 라벨은 반드시 {happy, sad, neutral, angry, anxiety, surprise} 집합만 사용한다. fear는 anxiety로 매핑할것.\n\n"
            "좋은 예시:\n"
            "- '주 초반에는 즐겁고 안정적인 날들이 많았지만, 목요일부터 감정상태가 급격히 나빠지고 있습니다.'\n"
            "- '이번 주는 전체적으로 즐거운 감정 혹은 안정된 상태를 유지하고 있어요.'\n"
            "- '최근 7일 동안 감정 분석 데이터가 없었습니다.'"
        ),
    }
    user = {
        "role": "user",
        "content": (
            "다음 날짜별 감정 목록을 바탕으로 주간 감정 추세를 한 문단(1~3문장)으로 요약해줘. "
            "초반/중반/후반 흐름을 구분하고, 감정 매핑 오류가 없도록 분노와 불안을 혼동하지 마. 불안은 anxiety로 표기해. "
            "데이터가 적어도 관찰 가능한 내용을 바탕으로 반드시 요약을 제공해줘.\n\n" + "\n".join(lines)
        ),
    }
    return [system, user]


def _build_frequency_prompt(user_name: str, counts: Dict[str, int]) -> List[Dict[str, str]]:
    """월간 빈도수 분석 프롬프트 구성"""
    # 사람이 읽기 쉬운 고정된 감정 라벨 순서와 함께 원시/정렬 정보를 모두 제공
    ordered_labels = ["happy", "sad", "neutral", "angry", "anxiety", "surprise"]
    # 키가 누락된 항목은 0으로 채움
    norm_counts = {k: int(counts.get(k, 0)) for k in ordered_labels}
    total = sum(norm_counts.values()) or 1
    # 백분율 계산(정수 반올림)
    pct = {k: int(round(v * 100.0 / total)) for k, v in norm_counts.items()}
    # 내림차순 정렬 목록 제공
    ranked = sorted(norm_counts.items(), key=lambda kv: kv[1], reverse=True)
    items = ", ".join([f"{k}:{v}" for k, v in ranked]) if counts else "(데이터 없음)"
    system = {
        "role": "system",
        "content": (
            "너는 노년층 혹은 장애인 케어 서비스의 감정 코치다. 한국어로 공감적이고 자연스럽게, 1~3문장으로 "
            "월간 감정 빈도 특성을 반드시 요약해라. 데이터가 적어도 관찰 가능한 내용을 바탕으로 요약을 제공해야 한다. "
            "추측하지 말고 관찰적인 표현만 사용하고, 과장 없이 사실 중심으로 서술해라. "
            "조언은 최소화하고 관찰 결과에 집중해라. 감정 라벨은 반드시 {happy, sad, neutral, angry, anxiety, surprise}만 사용하고, fear는 anxiety로 해석한다. "
            "다음 규칙을 반드시 준수하라: (1) 수치(rank)에 맞게 기술하고, 상위 감정들만 강조하라. (2) '상대적으로 높다/많다'라는 표현은 해당 감정의 빈도가 같은 달 내 다른 감정보다 순위가 높거나, 상위권(1~2위)이며 비율 차이가 10%p 이내일 때만 사용하라. "
            "(3) 슬픔(sad)과 불안(anxiety), 분노(angry)를 혼동하지 말고, 각 감정명은 정확히 표기하라. (4) 데이터가 적을 경우 과장하지 말고 '일부 확인'과 같은 표현을 사용하라.\n\n"
            "좋은 예시:\n"
            "- '10월은 평온하고 안정적인 마음으로 시작하셨네요! 다만, 슬픔, 불안과 같은 감정들이 일부 확인되는것으로 보입니다.'\n"
            "- '이번 달에는 화가 나는 감정이 다소 자주 나타났습니다. 이는 일상에서의 스트레스나 불만이 일부 확인된 것으로 보입니다.'\n"
            "- '이번 달에는 감정 분석 데이터가 없었습니다.'"
        ),
    }
    user = {
        "role": "user",
        "content": (
            f"대상 사용자: {user_name}\n"
            f"총합: {total}건\n"
            f"정렬(내림차순): {items}\n"
            f"백분율: happy={pct['happy']}%, sad={pct['sad']}%, neutral={pct['neutral']}%, angry={pct['angry']}%, anxiety={pct['anxiety']}%, surprise={pct['surprise']}%\n"
            "위의 수치에 정확히 기반하여 월간 감정 경향을 1~3문장으로 요약해줘. 순위/비율과 모순되는 표현은 사용하지 마."
        ),
    }
    return [system, user]


def get_weekly_result(session: Session, username: str, month: str, week: int, is_care: bool = False) -> str:
    """주간 종합분석 결과 메시지 생성"""
    from ..auth_service import get_auth_service
    from calendar import monthrange
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

    # 조회하고자 하는 주차의 기간 계산
    try:
        y, m = map(int, month.split("-"))
    except Exception:
        raise ValueError("month format YYYY-MM required")
    start_day = (week-1)*7+1
    end_day = min(week*7, monthrange(y, m)[1])
    start_date = datetime(y, m, start_day)
    end_date = datetime(y, m, end_day, 23, 59, 59)

    # 조회 기간 내 가장 최근 voice_composite_id 조회
    latest_vc = (
        session.query(VoiceComposite.voice_composite_id)
        .join(Voice, Voice.voice_id == VoiceComposite.voice_id)
        .filter(
            Voice.user_id == target_user.user_id,
            Voice.created_at >= start_date,
            Voice.created_at <= end_date,
        )
        .order_by(VoiceComposite.created_at.desc())
        .first()
    )
    latest_vc_id = latest_vc[0] if latest_vc else None

    # 데이터가 없으면 고정 메시지 반환 (OpenAI 호출 안 함)
    if latest_vc_id is None:
        fixed_message = "해당 주에는 감정분석 데이터가 없었습니다."
        # 캐시 조회
        cache = session.query(WeeklyResult).filter(WeeklyResult.user_id == target_user.user_id).first()
        if cache and cache.latest_voice_composite_id is None:
            return cache.message
        # 캐시 저장/갱신
        if cache:
            cache.message = fixed_message
            cache.latest_voice_composite_id = None
        else:
            session.add(WeeklyResult(
                user_id=target_user.user_id,
                latest_voice_composite_id=None,
                message=fixed_message,
            ))
        session.commit()
        return fixed_message

    # 캐시 조회
    cache = session.query(WeeklyResult).filter(WeeklyResult.user_id == target_user.user_id).first()
    if cache and cache.latest_voice_composite_id == latest_vc_id:
        return cache.message

    # 생성 후 캐시 저장/갱신
    by_day = _query_weekly_top_emotions(session, target_user.user_id, month, week)
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


def get_frequency_result(session: Session, username: str, month: str, is_care: bool = False) -> str:
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

    # 조회하고자 하는 월의 기간 계산
    try:
        y, m = map(int, month.split("-"))
    except Exception:
        raise ValueError("month format YYYY-MM required")
    from calendar import monthrange
    start_date = datetime(y, m, 1)
    # 다음 달 1일
    if m == 12:
        next_month = datetime(y + 1, 1, 1)
    else:
        next_month = datetime(y, m + 1, 1)
    end_date = next_month

    # 조회 기간 내 가장 최근 voice_composite_id 조회
    latest_vc = (
        session.query(VoiceComposite.voice_composite_id)
        .join(Voice, Voice.voice_id == VoiceComposite.voice_id)
        .filter(
            Voice.user_id == target_user.user_id,
            Voice.created_at >= start_date,
            Voice.created_at < end_date,
        )
        .order_by(VoiceComposite.created_at.desc())
        .first()
    )
    latest_vc_id = latest_vc[0] if latest_vc else None

    # 데이터가 없으면 고정 메시지 반환 (OpenAI 호출 안 함)
    if latest_vc_id is None:
        fixed_message = "해당 달에는 감정 분석 데이터가 없었습니다."
        # 캐시 조회
        cache = session.query(FrequencyResult).filter(FrequencyResult.user_id == target_user.user_id).first()
        if cache and cache.latest_voice_composite_id is None:
            return cache.message
        # 캐시 저장/갱신
        if cache:
            cache.message = fixed_message
            cache.latest_voice_composite_id = None
        else:
            session.add(FrequencyResult(
                user_id=target_user.user_id,
                latest_voice_composite_id=None,
                message=fixed_message,
            ))
        session.commit()
        return fixed_message

    # 캐시 조회
    cache = session.query(FrequencyResult).filter(FrequencyResult.user_id == target_user.user_id).first()
    if cache and cache.latest_voice_composite_id == latest_vc_id:
        return cache.message

    # 생성 후 캐시 저장/갱신
    counts = _query_month_emotion_counts(session, target_user.user_id, month)
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


