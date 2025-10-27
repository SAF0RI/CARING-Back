#!/bin/bash

# Caring Voice API 서버 배포 스크립트
# Ubuntu 환경 EC2에서 실행

set -e

echo "🚀 Caring Voice API 서버 배포 시작..."

# 1. 시스템 업데이트
echo "📦 시스템 패키지 업데이트..."
sudo apt-get update
sudo apt-get upgrade -y

# 2. Python 3.11 설치
echo "🐍 Python 3.11 설치..."
sudo apt-get install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3.11-dev python3-pip

# 3. 시스템 의존성 설치 (오디오 처리)
echo "📚 시스템 의존성 설치..."
sudo apt-get install -y \
    ffmpeg \
    libsndfile1 \
    libffi-dev \
    libssl-dev \
    build-essential \
    pkg-config \
    gcc \
    g++ \
    git \
    curl

# 4. 프로젝트 디렉토리 설정
echo "📁 프로젝트 디렉토리 설정..."
PROJECT_DIR="/home/ubuntu/caring-voice"
mkdir -p $PROJECT_DIR
cd $PROJECT_DIR

# 5. 가상 환경 생성
echo "🔧 가상 환경 생성..."
python3.11 -m venv venv
source venv/bin/activate

# 6. pip 업그레이드
echo "⬆️  pip 업그레이드..."
pip install --upgrade pip setuptools wheel

# 7. 프로젝트 파일 복사 (git clone 또는 scp 사용)
# 이 부분은 수동으로 또는 별도 스크립트로 처리
echo "📥 프로젝트 파일 복사 확인..."
# git clone <repository-url> .
# 또는 scp로 파일 복사

# 8. 의존성 설치
echo "📦 Python 의존성 설치..."
pip install -r requirements.txt

# 9. 환경 변수 설정
echo "⚙️  환경 변수 설정..."
if [ ! -f .env ]; then
    echo ".env 파일이 없습니다. 수동으로 생성하세요."
    echo "DB_HOST=your-rds-endpoint"
    echo "DB_PORT=3306"
    echo "DB_USER=admin"
    echo "DB_PASSWORD=your-password"
    echo "DB_NAME=caring_voice"
    echo "AWS_ACCESS_KEY_ID=your-key"
    echo "AWS_SECRET_ACCESS_KEY=your-secret"
    echo "AWS_REGION=ap-northeast-2"
    echo "S3_BUCKET_NAME=your-bucket"
    exit 1
fi

# 10. 데이터베이스 마이그레이션
echo "🔄 데이터베이스 마이그레이션..."
python -m alembic upgrade head

# 11. systemd 서비스 설정
echo "🔧 systemd 서비스 설정..."
sudo tee /etc/systemd/system/caring-voice.service > /dev/null <<EOF
[Unit]
Description=Caring Voice API Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
ExecStart=$PROJECT_DIR/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 12. 서비스 시작
echo "▶️  서비스 시작..."
sudo systemctl daemon-reload
sudo systemctl enable caring-voice
sudo systemctl start caring-voice

# 13. 상태 확인
echo "✅ 서비스 상태 확인..."
sleep 2
sudo systemctl status caring-voice

echo ""
echo "✅ Caring Voice API 서버 배포 완료!"
echo "📍 서버 주소: http://your-ec2-ip:8000"
echo "📚 API 문서: http://your-ec2-ip:8000/docs"
echo ""
echo "관리 명령어:"
echo "  - 서비스 시작: sudo systemctl start caring-voice"
echo "  - 서비스 중지: sudo systemctl stop caring-voice"
echo "  - 상태 확인: sudo systemctl status caring-voice"
echo "  - 로그 확인: sudo journalctl -u caring-voice -f"
