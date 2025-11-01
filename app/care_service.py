from sqlalchemy import func, extract
from .models import User, Voice, VoiceAnalyze
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
                self.db.query(VoiceAnalyze.top_emotion, func.count())
                .join(Voice, Voice.voice_id == VoiceAnalyze.voice_id)
                .filter(
                    Voice.user_id == user.user_id,
                    extract('year', Voice.created_at) == y,
                    extract('month', Voice.created_at) == m
                )
                .group_by(VoiceAnalyze.top_emotion)
                .all()
            )
            freq = {str(emotion): count for emotion, count in results if emotion}
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
                self.db.query(Voice, VoiceAnalyze)
                .join(VoiceAnalyze, Voice.voice_id == VoiceAnalyze.voice_id)
                .filter(
                    Voice.user_id == user.user_id,
                    Voice.created_at >= start_date,
                    Voice.created_at <= end_date,
                ).order_by(Voice.created_at.asc())
            )
            days = defaultdict(list)  # day: [emotion, ...]
            day_first = {}
            for v, va in q:
                d = v.created_at.date()
                em = va.top_emotion
                days[d].append(em)
                if d not in day_first:
                    day_first[d] = em  # 업로드 빠른 감정 미리 기억
            result = []
            for d in sorted(days.keys()):
                cnt = Counter(days[d])
                top, val = cnt.most_common(1)[0]
                # 동률 맞추기(동점시 가장 먼저 업로드한 감정을 top으로)
                top_emotions = [e for e, c in cnt.items() if c == val]
                selected = day_first[d] if len(top_emotions) > 1 and day_first[d] in top_emotions else top
                result.append({
                    "date": d.isoformat(),
                    "weekday": d.strftime("%a"),
                    "top_emotion": selected
                })
            return {"success": True, "weekly": result}
        except Exception as e:
            return {"success": False, "weekly": [], "message": f"error: {str(e)}"}
