# Lab 06 · Cloud Shell로 가상 네트워크 만들기

!!! info "실습 정보"
    - **주제**: Azure Cloud Shell + CLI로 네트워크 구성
    - **예상 시간**: 20분
    - **배우는 것**:
        1. Azure Cloud Shell 시작하기 (포털 내장 터미널)
        2. Azure CLI 명령어로 VNet·서브넷 만들기
        3. CLI 명령어로 리소스 조회 및 삭제

!!! warning "사전 준비"
    강사에게 배정받은 리소스 그룹이 있어야 합니다.
    Lab 01에서 설정한 리소스 그룹(`rg-student01` 등)을 사용합니다.

---

## 실습 목표

Lab 04에서는 **포털 UI**로 가상 네트워크를 만들었습니다.
이번에는 **Cloud Shell**을 열어 명령어 한 줄로 같은 결과를 만들어봅니다.

CLI를 쓰면 반복 작업을 자동화하거나, 동일한 환경을 빠르게 여러 번 배포할 수 있습니다.

---

## Step 1 · Cloud Shell 열기

Azure Portal 상단 오른쪽에 있는 **`>_`** 아이콘을 클릭합니다.

```
포털 상단 바: [검색창]  [🔔] [⚙️] [>_] [👤]
                                       ↑
                               이 아이콘 클릭
```

!!! tip "처음 Cloud Shell을 여는 경우"
    스토리지 계정 생성 여부를 묻는 팝업이 뜹니다.
    **"스토리지 만들기"** 또는 **"고급 설정"** 중 **스토리지 만들기**를 클릭합니다.
    강사 계정에 이미 스토리지가 있으면 팝업 없이 바로 열립니다.

1. **Bash** 를 선택합니다 (PowerShell이 선택되어 있으면 드롭다운에서 Bash로 변경).
2. 터미널이 열리면 아래와 같은 프롬프트가 보입니다.

```
yourname@Azure:~$
```

---

## Step 2 · 리소스 그룹 확인

먼저 현재 계정에서 보이는 리소스 그룹 목록을 확인합니다.

```bash
az group list --output table
```

!!! success "예상 출력"
    ```
    Name             Location       Status
    ---------------  -------------  ---------
    rg-student01     koreacentral   Succeeded
    ```
    강사에게 배정받은 리소스 그룹 이름을 확인합니다.

---

## Step 3 · 변수 설정

명령어마다 긴 이름을 반복 입력하지 않도록 **변수**에 저장합니다.

```bash
RG="rg-student01"       # 강사에게 배정받은 리소스 그룹으로 변경
VNET="vnet-shell-lab"
LOCATION="koreacentral"
```

!!! warning "주의"
    `RG=` 뒤의 `rg-student01` 부분을 **본인의 리소스 그룹 이름**으로 바꿔 입력하세요.

설정한 변수를 확인합니다.

```bash
echo "리소스 그룹: $RG"
echo "VNet 이름: $VNET"
echo "지역: $LOCATION"
```

---

## Step 4 · 가상 네트워크 만들기

VNet과 첫 번째 서브넷을 한 번에 만듭니다.

```bash
az network vnet create \
  --resource-group $RG \
  --name $VNET \
  --location $LOCATION \
  --address-prefix 10.1.0.0/16 \
  --subnet-name subnet-frontend \
  --subnet-prefix 10.1.0.0/24
```

!!! tip "명령어 설명"
    | 옵션 | 설명 |
    |------|------|
    | `--resource-group` | 리소스를 만들 리소스 그룹 |
    | `--name` | VNet 이름 |
    | `--address-prefix` | VNet 전체 주소 범위 (65,536개 IP) |
    | `--subnet-name` | 기본 서브넷 이름 |
    | `--subnet-prefix` | 기본 서브넷 범위 (256개 IP) |

!!! success "예상 결과"
    JSON 형태로 생성된 VNet 정보가 출력됩니다.
    `"provisioningState": "Succeeded"` 가 보이면 성공입니다.

---

## Step 5 · 백엔드 서브넷 추가

```bash
az network vnet subnet create \
  --resource-group $RG \
  --vnet-name $VNET \
  --name subnet-backend \
  --address-prefix 10.1.1.0/24
```

---

## Step 6 · 생성된 리소스 확인

### VNet 정보 조회

```bash
az network vnet show \
  --resource-group $RG \
  --name $VNET \
  --output table
```

### 서브넷 목록 조회

```bash
az network vnet subnet list \
  --resource-group $RG \
  --vnet-name $VNET \
  --output table
```

!!! success "예상 출력"
    ```
    AddressPrefix    Name              ProvisioningState
    ---------------  ----------------  -------------------
    10.1.0.0/24      subnet-frontend   Succeeded
    10.1.1.0/24      subnet-backend    Succeeded
    ```

---

## Step 7 · 포털에서 결과 확인

CLI로 만든 리소스가 포털에도 반영됩니다.

1. Azure Portal 상단 검색창에 **`가상 네트워크`** 를 입력합니다.
2. 목록에서 **`vnet-shell-lab`** 을 클릭합니다.
3. 왼쪽 메뉴 **서브넷**을 클릭하여 두 서브넷을 확인합니다.

!!! tip "CLI ↔ 포털 동기화"
    CLI, 포털, ARM 템플릿, Terraform 중 어느 방법으로 만들어도
    Azure Resource Manager가 동일하게 처리합니다.
    포털에서 바꾸면 CLI에도 즉시 반영됩니다.

---

## Step 8 · 리소스 삭제

실습이 끝난 VNet을 삭제합니다.

```bash
az network vnet delete \
  --resource-group $RG \
  --name $VNET \
  --yes
```

삭제됐는지 확인합니다.

```bash
az network vnet list \
  --resource-group $RG \
  --output table
```

출력이 비어 있으면 삭제 완료입니다.

---

## ✅ 완료 확인

- [ ] Cloud Shell을 Bash 모드로 열었다
- [ ] `az group list` 로 리소스 그룹을 확인했다
- [ ] `az network vnet create` 로 VNet을 만들었다
- [ ] `subnet-frontend`, `subnet-backend` 두 서브넷을 확인했다
- [ ] 포털에서도 생성된 VNet을 확인했다
- [ ] `az network vnet delete` 로 정리했다

---

## 💡 핵심 정리

| 개념 | 설명 |
|------|------|
| **Cloud Shell** | 브라우저 안에서 실행되는 Azure 전용 터미널. 설치 불필요 |
| **Azure CLI (`az`)** | Azure 리소스를 명령어로 관리하는 도구 |
| `az group list` | 구독에 있는 리소스 그룹 목록 조회 |
| `az network vnet create` | 가상 네트워크 생성 |
| `az network vnet subnet create` | 서브넷 추가 |
| `--output table` | 결과를 JSON 대신 표 형식으로 보기 |

!!! note "CLI vs 포털 — 언제 무엇을?"
    - **포털**: 처음 배울 때, 시각적으로 확인할 때
    - **CLI**: 반복 배포, 스크립트 자동화, 빠른 작업

    실무에서는 인프라를 코드로 관리하는 **IaC(Infrastructure as Code)** 를 위해 CLI나 Bicep/Terraform을 많이 씁니다.
