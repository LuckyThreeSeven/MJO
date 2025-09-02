import cv2
import numpy as np
import time
from datetime import datetime
import subprocess

# --- 설정값 ---
CAMERA_INDEX = 0
MOTION_THRESHOLD = 500
STREAM_COMMAND = [
    "ffmpeg",
    "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "640x480", "-r", "30", "-i", "-",
    # --- 수정된 부분: yuv420p 픽셀 포맷 명시 ---
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", "-tune", "zerolatency", "-b:v", "800k",
    "-f", "mpegts", "srt://127.0.0.1:9000?latency=1000000"
]
INITIAL_STREAM_DURATION = 10
EXTEND_STREAM_DURATION = 5
MOTION_COOLDOWN = 5
PROCESSING_SCALE = 0.5
PROCESSING_FPS = 10

# --- 변수 초기화 ---
prev_frame = None
frame_count = 0
CAP_FPS = 30
streaming_process = None
is_streaming = False
stream_end_time = 0
cooldown_end_time = 0

cap = cv2.VideoCapture(CAMERA_INDEX)
if not cap.isOpened():
    print("오류: 카메라를 열 수 없습니다.")
    exit()

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
cap.set(cv2.CAP_PROP_FPS, CAP_FPS)

print("움직임 감지 및 이벤트 기반 스트리밍을 시작합니다... (종료하려면 'q' 키를 누르세요)")

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.1)
            continue

        current_time = time.time()
        frame_count += 1
        
        if frame_count % (CAP_FPS // PROCESSING_FPS) == 0:
            if current_time > cooldown_end_time:
                small_frame = cv2.resize(frame, (0, 0), fx=PROCESSING_SCALE, fy=PROCESSING_SCALE)
                gray_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
                gray_frame = cv2.GaussianBlur(gray_frame, (21, 21), 0)

                if prev_frame is not None:
                    frame_delta = cv2.absdiff(prev_frame, gray_frame)
                    thresh = cv2.threshold(frame_delta, 30, 255, cv2.THRESH_BINARY)[1]
                    contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    
                    motion_detected_this_frame = False
                    for contour in contours:
                        if cv2.contourArea(contour) < MOTION_THRESHOLD:
                            continue
                        motion_detected_this_frame = True
                        (x, y, w, h) = [int(c / PROCESSING_SCALE) for c in cv2.boundingRect(contour)]
                        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

                    if motion_detected_this_frame:
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 움직임 감지됨!")
                        cooldown_end_time = current_time + MOTION_COOLDOWN
                        if not is_streaming:
                            print(f"  >> 스트리밍 시작! (기본 {INITIAL_STREAM_DURATION}초)")
                            streaming_process = subprocess.Popen(STREAM_COMMAND, stdin=subprocess.PIPE)
                            is_streaming = True
                            stream_end_time = current_time + INITIAL_STREAM_DURATION
                        else:
                            stream_end_time += EXTEND_STREAM_DURATION
                            print(f"  >> 스트리밍 중 움직임 감지! ({EXTEND_STREAM_DURATION}초 연장)")
                
                prev_frame = gray_frame

        if is_streaming:
            if current_time < stream_end_time:
                try:
                    streaming_process.stdin.write(frame.tobytes())
                except (IOError, BrokenPipeError):
                    print("FFmpeg 프로세스 연결 오류. 스트리밍을 종료합니다.")
                    is_streaming = False
                    if streaming_process:
                        streaming_process.terminate()
                        streaming_process.wait()
                        streaming_process = None
            else:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 스트리밍 시간 종료.")
                is_streaming = False
                if streaming_process:
                    streaming_process.stdin.close()
                    streaming_process.terminate()
                    streaming_process.wait()
                    streaming_process = None
        
        # --- 화면에 표시되는 텍스트를 영어로 변경 ---
        status_text = "STABLE"
        status_color = (0, 255, 0)
        
        if is_streaming:
            remaining_time = max(0, int(stream_end_time - current_time))
            status_text = f"STREAMING ({remaining_time}s left)"
            status_color = (0, 0, 255)
        elif current_time < cooldown_end_time:
            remaining_time = max(0, int(cooldown_end_time - current_time))
            status_text = f"COOLDOWN ({remaining_time}s left)"
            status_color = (0, 255, 255)

        cv2.putText(frame, f"STATUS: {status_text}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, status_color, 2)
        cv2.imshow("Motion Detection Client", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        
except KeyboardInterrupt:
    print("사용자에 의해 프로그램이 중단되었습니다.")
finally:
    if streaming_process:
        streaming_process.stdin.close()
        streaming_process.terminate()
        streaming_process.wait()
    cap.release()
    cv2.destroyAllWindows()
    print("카메라를 해제하고 프로그램을 종료합니다.")

