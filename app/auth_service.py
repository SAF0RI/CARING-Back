import secrets
import string
from datetime import date, datetime
from typing import Optional
from sqlalchemy.orm import Session
from .models import User


def generate_user_code(length: int = 8) -> str:
    """사용자 코드 자동 생성 (영문 대소문자 + 숫자)"""
    characters = string.ascii_letters + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))


def hash_password(password: str) -> str:
    """비밀번호 해시 (bcrypt)"""
    import bcrypt
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """비밀번호 검증"""
    import bcrypt
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


class AuthService:
    """인증 관련 서비스"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def signup(self, name: str, birthdate: str, username: str, password: str, 
               role: str, connecting_user_code: Optional[str] = None) -> dict:
        """
        회원가입 처리
        
        Args:
            name: 사용자 이름
            birthdate: 생년월일 (YYYY.MM.DD)
            username: 아이디
            password: 비밀번호
            role: 역할 (USER 또는 CARE)
            connecting_user_code: CARE 역할일 때 연결할 사용자 username
            
        Returns:
            dict: 회원가입 결과
        """
        try:
            # 1. 역할 검증
            if role not in ['USER', 'CARE']:
                return {
                    "success": False,
                    "error": "Invalid role. Must be 'USER' or 'CARE'"
                }
            
            # 2. USER 역할일 때는 connecting_user_code를 None으로 설정 (무시)
            if role == 'USER':
                connecting_user_code = None
            
            # 3. CARE 역할일 때 연결 사용자 코드 검증
            if role == 'CARE':
                if not connecting_user_code:
                    return {
                        "success": False,
                        "error": "connecting_user_code is required for CARE role"
                    }
                
                # 연결할 사용자가 존재하는지 확인 (username으로 조회)
                connecting_user = self.db.query(User).filter(
                    User.username == connecting_user_code
                ).first()
                
                if not connecting_user:
                    return {
                        "success": False,
                        "error": "Connecting user not found"
                    }
            
            # 4. 사용자명 중복 확인
            existing_user = self.db.query(User).filter(
                User.username == username
            ).first()
            
            if existing_user:
                return {
                    "success": False,
                    "error": "Username already exists"
                }
            
            # 5. 생년월일 파싱
            try:
                birth_date = datetime.strptime(birthdate, "%Y.%m.%d").date()
            except ValueError:
                return {
                    "success": False,
                    "error": "Invalid birthdate format. Use YYYY.MM.DD"
                }
            
            # 5. 사용자 코드 생성 (중복 방지)
            user_code = generate_user_code()
            while self.db.query(User).filter(User.user_code == user_code).first():
                user_code = generate_user_code()
            
            # 5-1. 비밀번호 해시
            hashed_password = hash_password(password)
            
            # 6. 사용자 생성
            user = User(
                user_code=user_code,
                username=username,
                password=hashed_password,
                role=role,
                name=name,
                birthdate=birth_date,
                connecting_user_code=connecting_user_code
            )
            
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
            
            return {
                "success": True,
                "user_code": user.user_code,
                "username": user.username,
                "name": user.name,
                "role": user.role,
                "created_at": user.created_at.isoformat()
            }
            
        except Exception as e:
            self.db.rollback()
            return {
                "success": False,
                "error": f"Signup failed: {str(e)}"
            }
    
    def get_user_by_code(self, user_code: str) -> Optional[User]:
        """사용자 코드로 사용자 조회"""
        return self.db.query(User).filter(User.user_code == user_code).first()
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """사용자명으로 사용자 조회"""
        return self.db.query(User).filter(User.username == username).first()
    
    
    def signin(self, username: str, password: str, role: str) -> dict:
        """
        로그인 처리
        
        Args:
            username: 아이디
            password: 비밀번호
            role: 역할 (USER 또는 CARE)
            
        Returns:
            dict: 로그인 결과
        """
        try:
            # 1. 역할 검증
            if role not in ['USER', 'CARE']:
                return {
                    "success": False,
                    "error": "Invalid role. Must be 'USER' or 'CARE'"
                }
            
            # 2. 사용자 조회
            user = self.db.query(User).filter(User.username == username).first()
            
            if not user:
                return {
                    "success": False,
                    "error": "User not found"
                }
            
            # 3. 역할 확인
            if user.role != role:
                return {
                    "success": False,
                    "error": "Invalid role for this user"
                }
            
            # 4. 비밀번호 검증
            if not verify_password(password, user.password):
                return {
                    "success": False,
                    "error": "Invalid password"
                }
            
            return {
                "success": True,
                "username": user.username,
                "name": user.name,
                "role": user.role,
                "user_code": user.user_code
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Signin failed: {str(e)}"
            }


def get_auth_service(db: Session) -> AuthService:
    """인증 서비스 인스턴스 생성"""
    return AuthService(db)
