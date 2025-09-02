## SimpleVideoStreamingService

ffmpeg 클라인언트 설치 (srt 프로토콜을 이용한 실시간 영상 전송)

```bash
brew install ffmpeg
```

&nbsp;

서버 실행

```bash
docker compose up --build
```

&nbsp;

서버 리스너 실행

```bash
curl -X POST http://localhost:8000/recordings/start
```

&nbsp;

클라이언트 실행 코드

```bash
ffmpeg -f avfoundation -framerate 30 -video_size 1280x720 -i "0:0" -c:v libx264 -preset ultrafast -c:a aac -f mpegts srt://127.0.0.1:9000
```

&nbsp;

## 실시간 영상 스트리밍
```bash
http://127.0.0.1:8000/viewer/{stream_id}
```