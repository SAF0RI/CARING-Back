"""그날의 대표 emotion 조회 서비스"""
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from datetime import datetime
from collections import Counter
from ..models import Voice, VoiceComposite, User


def get_top_emotion_for_date(session: Session, user_id: int, date_str: str) -> Optional[str]:
    """
    특정 날짜의 대표 emotion 조회 (weekly API와 동일한 로직)
    
    Args:
        session: 데이터베이스 세션
        user_id: 사용자 ID
        date_str: 날짜 문자열 (YYYY-MM-DD)
        
    Returns:
        그날의 대표 emotion (없으면 None)
    """
    try:
        # 날짜 파싱
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        start_datetime = datetime.combine(target_date, datetime.min.time())
        end_datetime = datetime.combine(target_date, datetime.max.time())
        
        # 해당 날짜의 voice_composite 조회
        q = (
            session.query(Voice, VoiceComposite)
            .join(VoiceComposite, Voice.voice_id == VoiceComposite.voice_id)
            .filter(
                Voice.user_id == user_id,
                Voice.created_at >= start_datetime,
                Voice.created_at <= end_datetime,
            ).order_by(Voice.created_at.asc())
        )
        
        emotions = []  # [emotion, ...]
        first_emotion = None  # 가장 먼저 업로드한 감정
        
        for v, vc in q:
            em = vc.top_emotion if vc else None
            emotions.append(em)
            if first_emotion is None:
                first_emotion = em
        
        if not emotions:
            return None
        
        # weekly API와 동일한 로직
        cnt = Counter(emotions)
        
        # Unknown이 아닌 감정이 하나라도 있으면 Unknown 제외
        non_unknown_cnt = {
            k: v for k, v in cnt.items() 
            if k and str(k).lower() not in ("unknown", "null", "none")
        }
        
        if non_unknown_cnt:
            # Unknown 제외하고 top_emotion 선택
            cnt_filtered = Counter(non_unknown_cnt)
            top, val = cnt_filtered.most_common(1)[0]
            top_emotions = [e for e, c in cnt_filtered.items() if c == val]
            
            # 가장 먼저 업로드한 Unknown 제외된 감정 찾기
            first_non_unknown = None
            for em in emotions:
                if em and str(em).lower() not in ("unknown", "null", "none"):
                    first_non_unknown = em
                    break
            
            selected = first_non_unknown if len(top_emotions) > 1 and first_non_unknown in top_emotions else top
        else:
            # 모든 감정이 Unknown인 경우에만 Unknown 반환
            top, val = cnt.most_common(1)[0]
            top_emotions = [e for e, c in cnt.items() if c == val]
            selected = first_emotion if len(top_emotions) > 1 and first_emotion in top_emotions else top
        
        # fear -> anxiety 변환 (출력용)
        if selected and str(selected) == "fear":
            selected = "anxiety"
        
        return selected
        
    except ValueError:
        # 날짜 형식 오류
        return None
    except Exception:
        return None

