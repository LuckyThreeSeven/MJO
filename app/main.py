import os
import uuid
import subprocess
import asyncio
from datetime import datetime

from fastapi import FastAPI, BackgroundTasks
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# --- 환경 변수 및 DB 설정 ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/videodb")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- SQLAlchemy 모델 정의 ---
class Video(Base):
    __tablename__ = "videos"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, unique=True, index=True)
    filepath = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

# DB 테이블 생성 (앱 시작 시 한번만)
Base.metadata.create_all(bind=engine)

app = FastAPI()

# --- 백그라운드 작업 함수 ---
async def process_recording(filename: str, process: asyncio.subprocess.Process):
    """
    FFmpeg 프로세스가 종료될 때까지 기다렸다가 DB에 저장하는 함수
    """
    await process.wait()  # FFmpeg 프로세스가 끝날 때까지 비동기적으로 대기
    
    print(f"Recording finished for {filename}. Process exited with code {process.returncode}.")
    
    # 프로세스가 정상 종료되었을 때만 DB에 기록
    if process.returncode == 0:
        db = SessionLocal()
        try:
            new_video = Video(
                filename=filename,
                filepath=f"/recordings/{filename}"
            )
            db.add(new_video)
            db.commit()
            print(f"Successfully saved metadata for {filename} to DB.")
        finally:
            db.close()

# --- API 엔드포인트 ---
@app.post("/recordings/start")
async def start_recording(background_tasks: BackgroundTasks):
    """
    녹화를 시작하고 클라이언트가 접속할 SRT 주소를 반환합니다.
    """
    stream_id = str(uuid.uuid4())
    filename = f"{stream_id}.mp4"
    filepath = f"/recordings/{filename}"
    
    # SRT 리스너로 동작하는 FFmpeg 명령어
    # 컨테이너 내부의 9000번 UDP 포트에서 SRT 연결을 기다림
    command = [
        "ffmpeg",
        "-i", "srt://:9000?mode=listener&latency=1000000",
        "-c", "copy",          # 비디오/오디오 재인코딩 없이 그대로 복사
        "-f", "mp4",           # MP4 컨테이너 형식으로 저장
        filepath
    ]

    # 비동기 서브프로세스로 FFmpeg 실행
    process = await asyncio.create_subprocess_exec(*command)
    
    print(f"Started FFmpeg listener for {filename} with PID {process.pid}")

    # FFmpeg 프로세스 종료를 감지하고 DB에 저장하는 작업을 백그라운드에 추가
    background_tasks.add_task(process_recording, filename, process)
    
    return {
        "message": "SRT listener started. Please start streaming.",
        "stream_id": stream_id,
        "srt_url": "srt://<YOUR_SERVER_IP>:9000" # 클라이언트에게 안내할 주소
    }

@app.get("/videos")
def get_videos():
    """
    DB에 저장된 영상 목록을 반환합니다.
    """
    db = SessionLocal()
    videos = db.query(Video).all()
    db.close()
    return videos