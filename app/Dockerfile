# 1. 파이썬 베이스 이미지
FROM python:3.10-slim

# 2. 시스템에 FFmpeg 설치 (가장 중요)
RUN apt-get update && apt-get install -y ffmpeg

# 3. 작업 디렉토리 설정
WORKDIR /app

# 4. 파이썬 라이브러리 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 앱 소스코드 복사
COPY . .

# 6. 컨테이너 실행 시 uvicorn 실행 (docker-compose에서 오버라이드)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
