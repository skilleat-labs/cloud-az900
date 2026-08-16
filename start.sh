#!/bin/bash
# AZ-900 Quiz Application Startup Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================="
echo "  AZ-900 모의고사 서버 시작"
echo "========================================="

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found"
    exit 1
fi

# Create virtual environment if not exists
if [ ! -d ".venv" ]; then
    echo "[1/3] 가상환경 생성 중..."
    python3 -m venv .venv
fi

# Activate venv
source .venv/bin/activate

# Install dependencies
echo "[2/3] 의존성 설치 중..."
pip install -q -r requirements.txt

# Check .env
if grep -q "your_key_here" .env 2>/dev/null; then
    echo ""
    echo "⚠️  주의: .env 파일에서 ANTHROPIC_API_KEY를 설정해주세요."
    echo "   Claude 해설 기능은 API 키 없이는 동작하지 않습니다."
    echo ""
fi

echo "[3/3] 서버 시작 중..."
echo ""
echo "  브라우저에서 열기: http://localhost:8000"
echo "  종료: Ctrl+C"
echo ""

# Start server
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
