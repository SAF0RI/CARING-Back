from sqlalchemy import func, extract
from .models import User, Voice, VoiceComposite
from .auth_service import get_auth_service
from datetime import datetime, timedelta
from collections import Counter, defaultdict

class CareService:
    def __init__(self, db):
        self.db = db
        self.auth_service = get_auth_service(db)

    def get_emotion_monthly_frequency(self, care_username: str, month: str) -> dict:
        """
        보호자 페이지: 연결 유저의 한달간 top_emotion 집계 반환
        :param care_username: 보호자 아이디
        :param month: 'YYYY-MM'
        :return: {success, frequency: {emotion: count, ...}}
        """
        try:
            care = self.auth_service.get_user_by_username(care_username)
            if not care or care.role != 'CARE' or not care.connecting_user_code:
                return {"success": False, "frequency": {}, "message": "Care user not found or no connection."}
            user = self.db.query(User).filter(User.username == care.connecting_user_code).first()
            if not user:
                return {"success": False, "frequency": {}, "message": "Connected user not found."}
            try:
                y, m = map(int, month.split("-"))
            except Exception:
                return {"success": False, "frequency": {}, "message": "month format YYYY-MM required"}
            results = (
                self.db.query(VoiceComposite.top_emotion, func.count())
                .join(Voice, Voice.voice_id == VoiceComposite.voice_id)
                .filter(
                    Voice.user_id == user.user_id,
                    extract('year', Voice.created_at) == y,
                    extract('month', Voice.created_at) == m,
                    VoiceComposite.top_emotion.isnot(None)  # null 제외
                )
                .group_by(VoiceComposite.top_emotion)
                .all()
            )
            # fear -> anxiety 변환 (출력용)
            freq = {}
            for emotion, count in results:
                if emotion:
                    key = "anxiety" if str(emotion) == "fear" else str(emotion)
                    freq[key] = count
            return {"success": True, "frequency": freq}
        except Exception as e:
            return {"success": False, "frequency": {}, "message": f"error: {str(e)}"}

    def get_emotion_weekly_summary(self, care_username: str, month: str, week: int) -> dict:
        """
        보호자 페이지: 연결 유저의 월/주차별 요일별 top 감정 요약 반환
        :param care_username: 보호자 아이디
        :param month: YYYY-MM
        :param week: 1~5 (1주차~5주차)
        :return: {success, weekly: [{day: "2025-10-02", weekday: "Thu", top_emotion: "happy"}, ...]}
        """
        try:
            care = self.auth_service.get_user_by_username(care_username)
            if not care or care.role != 'CARE' or not care.connecting_user_code:
                return {"success": False, "weekly": [], "message": "Care user not found or no connection."}
            user = self.db.query(User).filter(User.username == care.connecting_user_code).first()
            if not user:
                return {"success": False, "weekly": [], "message": "Connected user not found."}
            try:
                y, m = map(int, month.split("-"))
            except Exception:
                return {"success": False, "weekly": [], "message": "month format YYYY-MM required"}
            # 주차 구간 계산
            from calendar import monthrange
            start_day = (week-1)*7+1
            end_day = min(week*7, monthrange(y, m)[1])
            start_date = datetime(y, m, start_day)
            end_date = datetime(y, m, end_day, 23, 59, 59)
            # 요일별 group
            q = (
                self.db.query(Voice, VoiceComposite)
                .join(VoiceComposite, Voice.voice_id == VoiceComposite.voice_id)
                .filter(
                    Voice.user_id == user.user_id,
                    Voice.created_at >= start_date,
                    Voice.created_at <= end_date,
                ).order_by(Voice.created_at.asc())
            )
            days = defaultdict(list)  # day: [emotion, ...]
            day_first = {}
            for v, vc in q:
                d = v.created_at.date()
                em = vc.top_emotion if vc else None
                days[d].append(em)
                if d not in day_first:
                    day_first[d] = em  # 업로드 빠른 감정 미리 기억
            result = []
            for d in sorted(days.keys()):
                cnt = Counter(days[d])
                # Unknown이 아닌 감정이 하나라도 있으면 Unknown 제외
                non_unknown_cnt = {k: v for k, v in cnt.items() if k and str(k).lower() not in ("unknown", "null", "none")}
                if non_unknown_cnt:
                    # Unknown 제외하고 top_emotion 선택
                    cnt_filtered = Counter(non_unknown_cnt)
                    top, val = cnt_filtered.most_common(1)[0]
                    top_emotions = [e for e, c in cnt_filtered.items() if c == val]
                    # day_first에서도 Unknown 제외된 감정 중 첫 번째 찾기
                    first_non_unknown = None
                    for em in days[d]:
                        if em and str(em).lower() not in ("unknown", "null", "none"):
                            first_non_unknown = em
                            break
                    selected = first_non_unknown if len(top_emotions) > 1 and first_non_unknown in top_emotions else top
                else:
                    # 모든 감정이 Unknown인 경우에만 Unknown 반환
                    top, val = cnt.most_common(1)[0]
                    top_emotions = [e for e, c in cnt.items() if c == val]
                    selected = day_first[d] if len(top_emotions) > 1 and day_first[d] in top_emotions else top
                # fear -> anxiety 변환 (출력용)
                top_emotion_display = "anxiety" if selected and str(selected) == "fear" else selected
                result.append({
                    "date": d.isoformat(),
                    "weekday": d.strftime("%a"),
                    "top_emotion": top_emotion_display
                })
            return {"success": True, "weekly": result}
        except Exception as e:
            return {"success": False, "weekly": [], "message": f"error: {str(e)}"}
