#!/bin/bash

set -e

echo "🔄 Caring Voice API 서버 재시작(개발 모드, reload 포함)"

PROJECT_DIR="/home/ubuntu/caring-voice"
cd $PROJECT_DIR

echo "🛑 기존 uvicorn 프로세스 종료"
pkill -f "uvicorn app.main:app" || true
sleep 1

echo "📦 가상환경 활성화"
source venv/bin/activate

if [ ! -f .env ]; then
  echo "❌ .env 파일이 없습니다!"
  exit 1
fi

echo "🚀 서버 시작 중 (dev, reload)"
nohup uvicorn app.main:app \
  --host 0.0.0.0 --port 8000 \
  --reload \
  --reload-include '*.py' \
  --reload-include '*.yaml' --reload-include '*.yml' \
  --reload-exclude 'venv/*' \
  --reload-exclude 'site-packages/*' \
  --reload-exclude 'botocore/*' \
  > server.log 2>&1 &
SERVER_PID=$!

echo "⏳ 서버 시작 대기"
sleep 3

if ps -p $SERVER_PID > /dev/null; then
  echo "✅ 서버 실행 중 (PID: $SERVER_PID)"
  if curl -s http://localhost:8000/health > /dev/null; then
    echo "✅ 헬스체크 OK"
  else
    echo "⚠️  실행 중이나 응답 없음"
  fi
else
  echo "❌ 서버 시작 실패"
  tail -n 100 server.log || true
  exit 1
fi



