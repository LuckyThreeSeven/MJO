# SimpleVideoStreamingService
&nbsp;
서버 실행
`docker compose up --build`
&nbsp;
srt 프로토콜을 이용한 실시간 영상 전송(ffmpeg를 이용)
`brew install ffmpeg`
&nbsp;
서버 리스너 실행
`curl -X POST http://localhost:8000/recordings/start`
&nbsp;
클라이언트 실행 코드
`ffmpeg -f avfoundation -framerate 30 -video_size 1280x720 -i "0:0" -c:v libx264 -preset ultrafast -c:a aac -f mpegts srt://127.0.0.1:9000`
&nbsp;

