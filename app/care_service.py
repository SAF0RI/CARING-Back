from sqlalchemy import func, extract
from .models import User, Voice, VoiceAnalyze
from .auth_service import get_auth_service

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
            user = self.db.query(User).filter(User.user_code == care.connecting_user_code).first()
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
