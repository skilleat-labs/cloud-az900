# Lab 07 · Cloud Shell로 리소스 정리

!!! info "실습 정보"
    - **주제**: Azure Cloud Shell로 실습 리소스 일괄 삭제
    - **예상 시간**: 5분
    - **배우는 것**:
        1. 리소스 그룹 안 리소스 목록 확인
        2. Cloud Shell 명령어 한 줄로 전체 삭제

!!! warning "이 실습은 마지막에 진행하세요"
    리소스 그룹 안의 **모든 리소스가 삭제**됩니다.
    VM, VNet, 스토리지, 공용 IP, 디스크 등 지금까지 만든 것이 전부 사라집니다.

---

## 실습 목표

모든 실습이 끝난 뒤 Cloud Shell 명령어 한 줄로 리소스 그룹 안 리소스를 깔끔하게 정리합니다.

포털에서 하나씩 클릭해서 지우는 것보다 훨씬 빠르고, 실수로 빠뜨리는 리소스가 없습니다.

---

## Step 1 · Cloud Shell 열기

Azure Portal 상단의 **`>_`** 아이콘을 클릭합니다.

**Bash** 모드를 선택합니다.

---

## Step 2 · 현재 리소스 확인

삭제 전에 어떤 리소스가 있는지 먼저 확인합니다.

```bash
RG="test##-rg"    # ##을 본인 번호로 변경 (예: test21-rg)
```

```bash
az resource list --resource-group $RG --output table
```

!!! success "예상 출력"
    ```
    Name              ResourceType                         Location
    ----------------  -----------------------------------  ------------
    vm-##-web         Microsoft.Compute/virtualMachines    koreacentral
    vm-##-web_disk    Microsoft.Compute/disks              koreacentral
    vnet-##-lab       Microsoft.Network/virtualNetworks    koreacentral
    ...
    ```
    지금까지 만든 VM, 디스크, VNet 등이 목록에 나타납니다.

---

## Step 3 · 리소스 그룹 내 전체 삭제

```bash
az group delete --name $RG --yes
```

!!! warning "명령어 설명"
    | 옵션 | 설명 |
    |------|------|
    | `--name $RG` | 삭제할 리소스 그룹 이름 |
    | `--yes` | 확인 프롬프트 없이 바로 실행 |

    삭제 완료까지 **2~5분** 소요됩니다. 터미널에 프롬프트가 다시 나타나면 완료입니다.

---

## Step 4 · 삭제 확인

```bash
az resource list --resource-group $RG --output table
```

!!! success "이렇게 뜨면 성공!"
    ```
    (empty)
    ```
    또는 `ResourceNotFound` 오류가 뜨면 리소스 그룹과 내부 리소스가 모두 삭제된 것입니다.

---

## ✅ 완료 확인

- [ ] `az resource list` 로 리소스 목록을 확인했다
- [ ] `az group delete` 명령어를 실행했다
- [ ] 모든 리소스가 삭제됐다

---

## 💡 핵심 정리

| 명령어 | 설명 |
|--------|------|
| `az resource list --resource-group` | 리소스 그룹 내 리소스 목록 조회 |
| `az group delete --name --yes` | 리소스 그룹 및 내부 리소스 전체 삭제 |

!!! note "리소스 그룹 삭제 vs 내부 리소스만 삭제"
    - `az group delete` → 리소스 그룹 자체도 삭제
    - 리소스 그룹은 남기고 내부만 지우려면 각 리소스를 개별 삭제

    실습 환경에서는 그룹 통째로 삭제하는 것이 가장 깔끔합니다.
