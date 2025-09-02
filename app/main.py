import os
import uuid
import subprocess
import asyncio
from datetime import datetime
import glob # 파일 검색을 위해 glob 라이브러리 추가

from fastapi.responses import FileResponse # HTML 파일 서빙
from fastapi.staticfiles import StaticFiles # 정적 파일 서빙
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

# --- 정적 파일(HLS, 녹화 영상) 서빙 설정 ---
# /static 경로로 요청이 오면 recordings 폴더의 파일을 제공
app.mount("/static", StaticFiles(directory="/recordings"), name="static")

# --- 백그라운드 작업 함수 ---
async def process_recording(stream_id: str, process: asyncio.subprocess.Process):
    """
    FFmpeg 주 프로세스가 종료되면, 해당 스트림 ID로 생성된 모든 영상 조각을 DB에 저장
    """
    await process.wait()
    print(f"Main streaming process for stream_id {stream_id} has ended.")

    # recordings 폴더에서 해당 stream_id로 시작하는 모든 mp4 파일을 찾음
    segment_files = glob.glob(f"/recordings/{stream_id}-*.mp4")
    if not segment_files:
        print(f"No video segments found for stream_id {stream_id}.")
        return

    db = SessionLocal()
    try:
        for file_path in segment_files:
            filename = os.path.basename(file_path)
            # 중복 체크
            exists = db.query(Video).filter(Video.filename == filename).first()
            if not exists:
                new_video = Video(
                    filename=filename,
                    filepath=file_path,
                    stream_id=stream_id
                )
                db.add(new_video)
        db.commit()
        print(f"Successfully saved metadata for {len(segment_files)} segments to DB.")
    finally:
        db.close()

# --- API 엔드포인트 ---
@app.post("/recordings/start")
async def start_recording(background_tasks: BackgroundTasks):
    """
    10초 단위 세그먼트 녹화를 시작하고 클라이언트가 접속할 SRT 주소를 반환합니다.
    """
    stream_id = str(uuid.uuid4())
    live_dir = f"/recordings/live/{stream_id}"
    segment_dir = f"/recordings/segments" # 녹화 파일 저장 경로 분리
    os.makedirs(live_dir, exist_ok=True)
    os.makedirs(segment_dir, exist_ok=True)
    
    # --- FFmpeg 명령어: 두 개의 출력을 동시에 생성 ---
    command = [
        "ffmpeg",
        "-i", "srt://:9000?mode=listener&latency=1000000",
        
        # --- 비디오/오디오 코덱 설정 (재인코딩) ---
        "-c:v", "libx264",        # H.264 비디오 코덱으로 재인코딩
        "-preset", "ultrafast",   # CPU 사용량을 최소화하기 위한 프리셋
        "-tune", "zerolatency",   # 실시간 스트리밍에 최적화
        "-c:a", "aac",            # AAC 오디오 코덱으로 재인코딩
        "-ar", "44100",           # 오디오 샘플링 레이트 지정
        "-g", "60",               # 2초마다 키프레임 생성
        
        # --- 출력 1: MPEG-DASH 실시간 스트리밍 ---
        "-f", "dash",
        "-window_size", "5",        # 재생 목록에 유지할 세그먼트 수
        "-extra_window_size", "5",  # 버퍼를 위해 추가로 유지할 세그먼트 수
        "-remove_at_exit", "1",     # 종료 시 DASH 파일 삭제
        "-hls_playlist", "1",       # 하위 호환성을 위해 HLS 재생목록도 생성
        f"{live_dir}/live.mpd",


        # --- 출력 2: 10초 단위 MP4 녹화 ---
        "-f", "segment",
        "-segment_time", "10",
        "-reset_timestamps", "1", # 각 세그먼트의 타임스탬프를 0부터 시작하도록 리셋
        "-strftime", "1",
        "-segment_format", "mp4",
        f"{segment_dir}/{stream_id}-%Y%m%d_%H%M%S.mp4"

    ]

    process = await asyncio.create_subprocess_exec(*command)
    print(f"Started FFmpeg MPEG-DASH for stream_id {stream_id} with PID {process.pid}")

    # 백그라운드 작업에 stream_id를 전달
    background_tasks.add_task(process_recording, stream_id, process)
    
    return {
        "message": "MPEG-DASH live stream and recording started.",
        "stream_id": stream_id,
        "srt_url": "srt://<YOUR_SERVER_IP>:9000",
        "live_url": f"/static/live/{stream_id}/live.mpd", # .mpd로 변경
        "viewer_url": f"/viewer/{stream_id}"
    }

# --- 뷰어 페이지 서빙 엔드포인트 추가 ---
@app.get("/viewer/{stream_id}")
async def get_viewer_page(stream_id: str):
    return FileResponse('/frontend/index.html')

@app.get("/videos")
def get_videos():
    """
    DB에 저장된 영상 목록을 반환합니다.
    """
    db = SessionLocal()
    videos = db.query(Video).all()
    db.close()
    return videos

@app.get("/static/{dir1}/{stream_id}/{filename}")
async def get_streaming_file(dir1: str, stream_id: str, filename: str):
    file_path = f"/recordings/{dir1}/{stream_id}/{filename}"
    
    # .mpd 파일(재생 목록)의 경우 캐시 사용 안 함
    if filename.endswith('.mpd'):
        headers = {
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
        return FileResponse(file_path, headers=headers)
    
    # .m4s 파일(영상 조각) 등은 일반적인 FileResponse로 서빙
    return FileResponse(file_path)