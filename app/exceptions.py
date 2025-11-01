"""전역 예외 처리 모듈"""
from fastapi import HTTPException
from typing import Optional


class AppException(HTTPException):
    """애플리케이션 기본 예외 클래스"""
    def __init__(self, status_code: int, message: str):
        super().__init__(status_code=status_code, detail=message)
        self.message = message


class ValidationException(AppException):
    """검증 오류 (400)"""
    def __init__(self, message: str):
        super().__init__(status_code=400, message=message)


class RuntimeException(AppException):
    """런타임 오류 (400)"""
    def __init__(self, message: str):
        super().__init__(status_code=400, message=message)


class DatabaseException(AppException):
    """데이터베이스 오류 (500)"""
    def __init__(self, message: str):
        super().__init__(status_code=500, message=message)


class OutOfMemoryException(AppException):
    """메모리 부족 오류 (500)"""
    def __init__(self, message: str):
        super().__init__(status_code=500, message=message)


class InternalServerException(AppException):
    """기타 내부 서버 오류 (500)"""
    def __init__(self, message: str):
        super().__init__(status_code=500, message=message)

