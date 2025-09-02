import os
import time
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import FileResponse
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- DB 설정 ---
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Video(Base):
    __tablename__ = "videos"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, unique=True, index=True)
    filepath = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)
app = FastAPI()

RECORDING_PATH = "/recordings/segments"

class RecordingEventHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith('.mp4'):
            time.sleep(1) # 파일 쓰기가 완전히 끝날 때까지 잠시 대기
            filepath = event.src_path
            filename = os.path.basename(filepath)
            print(f"새로운 녹화 파일 감지: {filename}")
            self.save_to_db(filename, filepath)

    def save_to_db(self, filename: str, filepath: str):
        db = SessionLocal()
        try:
            exists = db.query(Video).filter(Video.filename == filename).first()
            if not exists:
                new_video = Video(filename=filename, filepath=filepath)
                db.add(new_video)
                db.commit()
                print(f"DB에 {filename} 정보 저장 완료.")
        finally:
            db.close()

@app.on_event("startup")
async def startup_event():
    os.makedirs(RECORDING_PATH, exist_ok=True)
    os.makedirs("/recordings/live", exist_ok=True)
    
    event_handler = RecordingEventHandler()
    observer = Observer()
    observer.schedule(event_handler, RECORDING_PATH, recursive=False)
    observer.start()
    print(f"{RECORDING_PATH} 폴더 감시를 시작합니다...")

@app.get("/viewer")
async def get_viewer_page():
    return FileResponse('/frontend/index.html')

@app.get("/videos")
def get_videos():
    db = SessionLocal()
    videos = db.query(Video).order_by(Video.created_at.desc()).all()
    db.close()
    return videos

# DASH 스트림 파일들을 서빙하는 엔드포인트
@app.get("/static/{dir1}/{filename}")
async def get_streaming_file(dir1: str, filename: str):
    file_path = f"/recordings/{dir1}/{filename}"
    if filename.endswith('.mpd'):
        headers = {'Cache-Control': 'no-cache'}
        return FileResponse(file_path, headers=headers)
    return FileResponse(file_path)

