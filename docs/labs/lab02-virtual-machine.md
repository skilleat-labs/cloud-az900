# Lab 03 · 가상 머신 + 웹 서버 데모

!!! info "실습 정보"
    - **주제**: IaaS(Infrastructure as a Service) 컴퓨팅
    - **예상 시간**: 20분
    - **배우는 것**:
        1. Azure 가상 머신(VM) 생성
        2. 사용자 스크립트로 웹 서버 자동 설치
        3. 브라우저에서 내 VM에 접속해보기

!!! warning "사전 준비"
    Lab 02에서 만든 가상 네트워크(`vnet-##-lab`)가 있어야 합니다.

---

## 실습 목표

VM을 만들면서 **사용자 스크립트**를 함께 넣어두면,
VM이 처음 시작될 때 자동으로 웹 서버를 설치하고 페이지를 띄웁니다.
배포가 끝난 뒤 브라우저에서 VM의 공용 IP로 접속하면 직접 만든 페이지가 뜹니다.

---

## Step 1 · 가상 머신 만들기 시작

1. Azure Portal 상단 검색창에 `가상 머신`을 입력합니다.
2. **가상 머신** 클릭 → **+ 만들기** → **Azure 가상 머신** 선택

---

## Step 2 · 기본 사항 설정

### 프로젝트 세부 정보

| 항목 | 값 |
|------|-----|
| 구독 | 강사가 제공한 구독 |
| 리소스 그룹 | `test##-rg` (본인 번호) |

### 인스턴스 세부 정보

| 항목 | 값 |
|------|-----|
| 가상 머신 이름 | `vm-##-web` (예: `vm-01-web`) |
| 지역 | Korea Central |
| 가용성 옵션 | 인프라 중복 필요 없음 |
| 이미지 | **Ubuntu Server 22.04 LTS - x64 Gen2** |
| 크기 | **Standard_B1s** |

!!! tip "이미지 선택 방법"
    이미지 항목 옆 **모든 이미지 보기** 클릭 → 검색창에 `Ubuntu 22.04` 입력 → **Ubuntu Server 22.04 LTS** 선택

### 관리자 계정

| 항목 | 값 |
|------|-----|
| 인증 유형 | 암호 |
| 사용자 이름 | `azureuser` |
| 암호 | `AzureLab2026!` |

### 인바운드 포트 규칙

| 항목 | 값 |
|------|-----|
| 공용 인바운드 포트 | 선택한 포트 허용 |
| 인바운드 포트 선택 | **HTTP (80)** 체크 |

---

## Step 3 · 네트워킹 설정

상단 탭에서 **네트워킹** 탭을 클릭합니다.

| 항목 | 값 |
|------|-----|
| 가상 네트워크 | `vnet-##-lab` (Lab 02에서 만든 VNet) |
| 서브넷 | `default` |
| 공용 IP | 새로 만들기 (기본값 유지) |

---

## Step 4 · 사용자 스크립트 넣기 ⭐

상단 탭에서 **고급** 탭을 클릭합니다.

**사용자 데이터** 항목을 찾아서 아래 스크립트를 붙여넣습니다.

```bash
#!/bin/bash
apt-get update -y
apt-get install -y nginx
cat > /var/www/html/index.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Azure VM 실습</title>
  <style>
    body { font-family: sans-serif; text-align: center; padding: 80px 20px;
           background: #0f1923; color: #e8f4fd; margin: 0; }
    h1 { color: #50e6ff; font-size: 2.8em; margin-bottom: 16px; }
    p { font-size: 1.2em; color: #a8c4d8; margin: 8px 0; }
    .badge { display: inline-block; margin-top: 24px; padding: 10px 28px;
             background: #0078D4; border-radius: 8px; font-weight: bold; }
  </style>
</head>
<body>
  <h1>🎉 Azure VM 실습 성공!</h1>
  <p>이 페이지는 Azure 가상 머신에서 실행 중입니다.</p>
  <p>IaaS(Infrastructure as a Service) 체험 완료!</p>
  <div class="badge">AZ-900 실습</div>
</body>
</html>
EOF
systemctl enable nginx
systemctl start nginx
```

!!! tip "사용자 스크립트란?"
    VM이 **처음 부팅될 때 딱 한 번** 자동으로 실행되는 명령어 모음입니다.
    nginx 설치 → HTML 파일 작성 → nginx 시작 순서로 실행됩니다.

---

## Step 5 · 만들기

1. **검토 + 만들기** 탭 클릭
2. **유효성 검사 통과** 확인
3. **만들기** 클릭

!!! tip "배포 시간"
    Ubuntu VM은 약 **2~3분** 소요됩니다.
    배포 화면에서 VM, NIC, 공용 IP, 디스크가 순서대로 생성되는 것을 확인합니다.

4. 완료 후 **리소스로 이동** 클릭

---

## Step 6 · 공용 IP 확인

VM 개요 페이지에서 **공용 IP 주소**를 찾아 복사합니다.

```
예: 20.249.xxx.xxx
```

---

## Step 7 · 브라우저에서 접속 🌐

새 탭을 열고 주소창에 입력합니다.

```
http://공용IP주소
```

!!! success "이렇게 뜨면 성공!"
    파란 배경에 **"🎉 Azure VM 실습 성공!"** 페이지가 보이면 완료입니다.

!!! warning "안 뜨는 경우"
    스크립트 실행에 **1~2분** 더 걸릴 수 있습니다. 잠시 후 새로고침(F5) 해보세요.
    `https://` 가 아닌 **`http://`** 로 접속해야 합니다.

---

## Step 8 · VM 중지 (비용 절감)

실습이 끝나면 VM을 반드시 중지합니다.

1. VM 개요 페이지 상단 **중지** 버튼 클릭
2. **확인** 클릭
3. 상태가 **"중지됨(할당 취소됨)"** 으로 바뀔 때까지 대기 (약 1분)

!!! warning "중지 vs 할당 취소"
    | 상태 | 컴퓨팅 비용 |
    |------|------------|
    | 실행 중 | 발생 |
    | 중지됨 | **발생** (주의!) |
    | 중지됨(할당 취소됨) | 없음 |

    Portal의 **중지** 버튼을 누르면 자동으로 할당 취소 상태가 됩니다.

---

## ✅ 완료 확인

- [ ] Ubuntu VM이 성공적으로 생성되었다
- [ ] 사용자 스크립트(nginx)를 넣었다
- [ ] 브라우저에서 `http://공용IP` 로 접속해 페이지를 확인했다
- [ ] VM을 중지(할당 취소)했다

---

## 💡 핵심 정리

| 개념 | 설명 |
|------|------|
| **IaaS** | OS·소프트웨어를 직접 관리. VM이 대표적인 예 |
| **사용자 스크립트** | VM 첫 부팅 시 자동 실행되는 초기화 명령어 |
| **할당 취소** | VM을 완전히 반납해 컴퓨팅 비용을 멈추는 상태 |
| **nginx** | 가볍고 빠른 오픈소스 웹 서버. 정적 HTML 서빙에 많이 사용 |
