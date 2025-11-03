# Glances 사용 가이드

## 설치 완료
glances 3.4.0.3 버전이 설치되었습니다.

## 기본 사용법

### 터미널에서 실시간 모니터링
```bash
glances
```

### 웹 서버 모드로 실행 (원격 접속 가능)
```bash
# 기본 포트(61208)로 실행
glances -w

# 특정 포트 지정
glances -w -p 61208

# 특정 IP에서만 접속 허용 (보안 강화)
glances -w -B 0.0.0.0 -p 61208
```

웹 브라우저에서 접속: `http://서버IP:61208`

### RESTful API 모드
```bash
glances -s
```

### CPU, 메모리, 디스크, 네트워크만 간단히 보기
```bash
glances --percpu
```

## 주요 단축키

- `q` 또는 `ESC`: 종료
- `h`: 도움말
- `c`: CPU 정보 표시/숨김
- `m`: 메모리 정보 표시/숨김
- `d`: 디스크 정보 표시/숨김
- `n`: 네트워크 정보 표시/숨김
- `p`: 프로세스 정렬 변경
- `w`: 경고 삭제
- `x`: 경고/중요 임계값 삭제

## 서비스로 실행

glances가 systemd 서비스로 자동 등록되어 있습니다.

```bash
# 서비스 시작
sudo systemctl start glances

# 서비스 중지
sudo systemctl stop glances

# 서비스 상태 확인
sudo systemctl status glances

# 부팅 시 자동 시작 활성화
sudo systemctl enable glances
```

## 백그라운드 실행

```bash
# nohup으로 백그라운드 실행
nohup glances -w > /dev/null 2>&1 &

# tmux/screen 사용
tmux new-session -d -s monitoring 'glances'
```

## 유용한 옵션

- `--refresh 2`: 2초마다 갱신 (기본값: 3초)
- `--disable-plugin docker`: Docker 플러그인 비활성화
- `--enable-plugin docker`: Docker 플러그인 활성화
- `--percpu`: CPU 코어별 사용량 표시
- `--process-short-name`: 짧은 프로세스 이름 표시
- `--time`: 시간 표시

## 예시: 웹 모드로 백그라운드 실행

```bash
# 웹 서버 모드로 백그라운드 실행
glances -w -B 0.0.0.0 -p 61208 &
```

브라우저에서 `http://서버IP:61208` 접속하여 모니터링 가능합니다.

