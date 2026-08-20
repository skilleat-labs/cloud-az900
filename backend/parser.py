"""
DOCX parser for AZ-900 quiz questions.
Handles yes/no and multiple choice question types.
"""

import re
import os
from pathlib import Path
from typing import Optional
from docx import Document


def strip_trailing_num(text: str) -> str:
    """Strip trailing digits (original question number) from answer text."""
    return re.sub(r'\s*\d+\s*$', '', text.strip()).strip()


# ── 오타/번역 교정 ──────────────────────────────────────────
_TYPO_FIXES = [
    # 오타
    (r'더블릭',                             '퍼블릭'),
    (r'리스스',                             '리소스'),
    (r'추천서에',                           '추천 내용에'),
    # 띄어쓰기
    (r'클라우드에 서\b',                    '클라우드에서'),
    (r'구성 해야',                          '구성해야'),
    (r'온 ?프레미스',                       '온프레미스'),
    # 문장부호 앞 불필요한 공백
    (r'\s+\.',                              '.'),
    (r'\s+\?',                              '?'),
    (r'\s+,',                               ','),
    # 보기 텍스트에 누출된 " 정답" 제거 (DOCX 원본 오류)
    (r'\s+정답\s*$',                        ''),
    # laaS 오타 수정 (소문자 l → 대문자 I)
    (r'\blaaS\b',                           'IaaS'),
    # 과도한 공백 → 단일 공백
    (r'[ \t]{2,}',                          ' '),
    # 어색한 번역 표현
    (r'게스트 사용자인 클라우드 리소스에 액세스할 수 있습니다',
     '게스트 사용자도 클라우드 리소스에 액세스할 수 있습니다'),
    (r'가상 머신을 확장할 때 자본 지출을 책임집니다',
     '가상 머신을 확장할 때 자본 지출을 부담합니다'),
    (r'식별해야 합니다\.',                  '식별하십시오.'),
    (r'포함해야 합니까\?',                  '포함해야 합니까?'),
    (r'응용 프로그램',                      '애플리케이션'),
    (r'사용해야 합니까\?',                  '사용해야 합니까?'),
]

def clean_text(text: str) -> str:
    """오타·번역 오류·띄어쓰기 교정을 일괄 적용한다."""
    for pattern, replacement in _TYPO_FIXES:
        text = re.sub(pattern, replacement, text)
    return text.strip()


def parse_yes_no_answer(answer_raw: str) -> list[str]:
    """
    Parse yes/no answer string into list of ['예', '아니오', ...].
    Handles separators: -, –, spaces, mixed.
    Also handles typos like '예0' (strip non-Korean chars between answers).
    """
    # Remove trailing question number
    cleaned = strip_trailing_num(answer_raw)

    # Split on common separators: -, –, or whitespace sequences
    # Also normalize em-dash variants
    cleaned = cleaned.replace('–', '-').replace('—', '-')

    # Split on dash or whitespace
    parts = re.split(r'[-\s]+', cleaned)

    results = []
    for part in parts:
        part = part.strip()
        # Extract 예 or 아니오 from the part (may have extra chars)
        if '아니오' in part:
            results.append('아니오')
        elif '예' in part:
            results.append('예')

    return results


def parse_multiple_choice_answer(answer_raw: str) -> 'int | list[int] | None':
    """
    Parse multiple choice answer. Returns 0-indexed integer or list of ints for multi-select.
    Answer raw may be '2\n184' or '1,4\n102', etc.
    First line contains the answer digit(s).
    """
    lines = answer_raw.strip().split('\n')
    first_line = lines[0].strip()

    # Check for comma-separated answers (e.g., '1,4') → multi-select
    if ',' in first_line:
        parts = re.split(r'[,\s]+', first_line.strip())
        indices = []
        for p in parts:
            m = re.match(r'^(\d+)', p.strip())
            if m:
                indices.append(int(m.group(1)) - 1)
        if len(indices) >= 2:
            return indices

    # Extract leading digit
    match = re.match(r'^(\d+)', first_line)
    if match:
        return int(match.group(1)) - 1  # Convert to 0-indexed

    return None


def extract_options_from_mc_text(question_lines: list[str]) -> tuple[str, list[str]]:
    """
    Given lines of a multiple choice question (after the Q prefix line),
    separate the question text from the options.

    For 'fill in the blank' type: question contains ________________
    Options are separate lines after the question.

    Heuristic: options are the last N lines that look like choices.
    """
    if not question_lines:
        return '', []

    # Join all lines first
    full_text = '\n'.join(question_lines)
    lines = [l.strip() for l in question_lines if l.strip()]

    if not lines:
        return full_text, []

    # Detect if this is a "fill in the blank" type
    # Pattern: first line(s) contain ________________
    blank_marker = '________________'

    if blank_marker in full_text:
        # Find the line with the blank - question ends after the first '.'  after the blank
        # Options come after
        # Typically: "설명을 완성하는 답을 선택하십시오.\nAzure China ________________ .\nOption1\nOption2..."
        question_parts = []
        options = []
        found_end_of_question = False
        skip_next = False

        for i, line in enumerate(lines):
            if skip_next:
                skip_next = False
                continue
            if found_end_of_question:
                options.append(line)
            elif blank_marker in line:
                question_parts.append(line)
                # If blank line ends with ',' the sentence continues on the next line
                if line.rstrip().endswith(',') and i + 1 < len(lines):
                    question_parts.append(lines[i + 1])
                    skip_next = True
                found_end_of_question = True
            else:
                question_parts.append(line)

        question = '\n'.join(question_parts)
        return question, options

    # "설명을 완성하는" 문제인데 blank_marker가 없는 경우:
    # 두 번째 줄이 완성할 문장(문제 텍스트)이고 나머지가 선택지
    # 예: "설명을 완성하는 답을 선택하십시오.\n회사의 규정 준수 보고서는 다음 위치에서 볼 수 있습니다.\nAzure Advisor\n..."
    if lines and '설명을 완성하는' in lines[0] and len(lines) >= 3:
        # 두 번째 줄이 ','로 끝나면 세 번째 줄도 문장 이어짐 (문제 텍스트의 연속)
        if len(lines) >= 4 and lines[1].rstrip().endswith(','):
            question = '\n'.join(lines[:3])
            options = lines[3:]
        else:
            question = '\n'.join(lines[:2])
            options = lines[2:]
        return question, options

    # For regular multiple choice questions:
    # The options are typically the last 3-4 lines
    # We need to figure out where the question ends and options begin
    #
    # Strategy: options are usually short (< 80 chars) and don't end with '?'
    # Question text often ends with '?' or '십시오.'
    #
    # Find the boundary by looking for lines that look like options (not question text)

    # Count lines - if we have exactly 4+ short lines at end, those are options
    # A typical question has 1-3 lines of question text, then 3-4 options

    # Simple approach: find where question ends
    # Question lines contain words like '무엇', '선택', '?', etc.
    # Look for the transition point

    # Try to detect options: last consecutive lines that don't end with '?' or '십시오'
    # and are relatively short

    # Walk from the end, accumulate option candidates
    option_candidates = []
    question_end_idx = len(lines)

    for i in range(len(lines) - 1, -1, -1):
        line = lines[i]
        # If this line looks like a question line, stop
        is_question_line = (
            line.endswith('?') or
            line.endswith('십시오.') or
            line.endswith('하십시오.') or
            line.endswith('습니까?') or
            '다음 중' in line or
            '무엇입니까' in line or
            '선택하십시오' in line or
            '권장해야' in line or
            len(line) > 100 or
            # 연결 문제의 항목 목록 ("용어 :", "장점 :", "서비스 :" 등)
            bool(re.match(r'^[가-힣]+ :', line))
        )

        if is_question_line and len(option_candidates) >= 2:
            question_end_idx = i + 1
            break

        option_candidates.insert(0, line)
    else:
        # If we didn't break, set boundary
        if len(option_candidates) >= 3:
            question_end_idx = len(lines) - len(option_candidates)

    # Ensure we have at most 5 options (some questions have 5)
    if len(option_candidates) > 5:
        # Too many "options" - adjust boundary
        excess = len(option_candidates) - 5
        question_end_idx += excess
        option_candidates = option_candidates[excess:]

    question = '\n'.join(lines[:question_end_idx])
    options = option_candidates

    # Fallback: if options empty or question empty, split at midpoint
    if not options or not question:
        mid = max(1, len(lines) - 4)
        question = '\n'.join(lines[:mid])
        options = lines[mid:]

    # Filter out instruction lines that leaked into options (e.g., "참고: ...")
    _OPTION_NOISE = ('참고:', '답변하려면', '지침:', '주의:')
    options = [o for o in options if not any(o.startswith(p) for p in _OPTION_NOISE)]

    return question, options


def parse_question_paragraph(q_text: str, a_text: str, q_index: int, exam_stem: str = '') -> dict:
    """
    Parse a single Q/A pair into structured data.

    q_text: full question paragraph text
    a_text: full answer paragraph text
    q_index: sequential index (for id generation)
    """
    # Extract Q number prefix: "Q1. 104. "
    # Then the rest is the question content
    q_match = re.match(r'^Q(\d+)\.\s+(\d+)\.\s*(.+)$', q_text, re.DOTALL)
    if not q_match:
        # Try without leading Q prefix
        q_match = re.match(r'^(\d+)\.\s*(.+)$', q_text, re.DOTALL)
        if q_match:
            q_seq = str(q_index + 1)
            orig_num = q_match.group(1)
            content = q_match.group(2)
        else:
            return None
    else:
        q_seq = q_match.group(1)
        orig_num = q_match.group(2)
        content = q_match.group(3)

    # Normalize content - split by newlines
    content_lines = [l.strip() for l in content.split('\n')]
    content_lines = [l for l in content_lines if l]

    # Determine question type
    # Check first line for yes/no indicators
    first_line = content_lines[0] if content_lines else ''

    is_yes_no = (
        '예 아니오 문제' in first_line or
        '예 아니오' in first_line
    )

    # Also check if content contains these markers anywhere in first portion
    if not is_yes_no and content_lines:
        combined_start = ' '.join(content_lines[:2])
        is_yes_no = '예 아니오' in combined_start

    if is_yes_no:
        return parse_yes_no_question(q_seq, orig_num, content_lines, a_text, exam_stem=exam_stem)  # returns list
    else:
        result = parse_multiple_choice_question(q_seq, orig_num, content_lines, a_text, exam_stem=exam_stem)
        return result if isinstance(result, list) else [result]


def parse_yes_no_question(q_seq: str, orig_num: str, content_lines: list[str], a_text: str, exam_stem: str = '') -> list[dict]:
    """Parse a yes/no type question into individual questions per statement."""
    statements = []
    for line in content_lines:
        if '예 아니오 문제' in line or line.strip() == '예 아니오':
            after = re.split(r'예 아니오 문제|예 아니오', line, maxsplit=1)
            if len(after) > 1 and after[1].strip():
                remaining = after[1].strip()
                for sub in remaining.split('\n'):
                    sub = sub.strip()
                    if sub:
                        statements.append(sub)
            continue
        if line.strip():
            statements.append(line.strip())

    answer_list = parse_yes_no_answer(a_text)
    while len(answer_list) < len(statements):
        answer_list.append('아니오')

    # Return one question dict per statement
    result = []
    for i, stmt in enumerate(statements):
        answer = _YES_NO_OVERRIDES.get((exam_stem, q_seq, i)) if exam_stem else None
        if answer is None:
            answer = answer_list[i] if i < len(answer_list) else '아니오'
        stmt_override = _YES_NO_STATEMENT_OVERRIDES.get((exam_stem, q_seq, i)) if exam_stem else None
        display_stmt = stmt_override if stmt_override else clean_text(stmt)
        result.append({
            'id': f'q{q_seq}_{i+1}',
            'original_num': orig_num,
            'type': 'yes_no',
            'question': display_stmt,
            'statements': [],
            'options': [],
            'answer': answer,
            'answer_index': None,
            'answer_text': None,
        })
    return result


# 정답 오버라이드: {(파일명 stem, q_seq): 0-indexed 정답 (int 또는 list[int] for multi_select)}
_ANSWER_OVERRIDES: dict[tuple[str, str], 'int | list[int]'] = {
    ('1-1_클라우드컴퓨팅_2부 (32문제)', '9'): 3,   # Azure China → 4번 (Microsoft Azure의 고유한 개별 인스턴스)
    ('2-2_컴퓨팅및네트워크_2부 (21문제)', '5'): 1,  # 온프레미스 서버 관리 → 2번 (Azure Arc)
    ('2-2_컴퓨팅및네트워크_2부 (21문제)', '12'): 0, # 컨테이너 인스턴스 분류 → 1번 (컴퓨팅 서비스)
    # 2-2 컴퓨팅및네트워크
    ('2-2_컴퓨팅및네트워크_2부 (21문제)', '4'): 3,  # Software Assurance → 4번 (index=3)
    # 2-3 스토리지서비스
    ('2-3_스토리지서비스_2부 (11문제)', '5'): 2,    # 프리미엄 블록 Blob → LRS만 지원 → 3번 (index=2)
    # 2-4 ID접근보안
    ('2-4_ID접근보안_2부 (16문제)', '1'): 1,        # SSO 제공 서비스 → Azure AD → 2번 (index=1, blank줄 제거 후)
    ('2-4_ID접근보안_2부 (16문제)', '2'): 2,        # 규정 요구사항 평가 → 클라우드용 Microsoft Defender → 3번 (index=2)
    ('2-4_ID접근보안_2부 (16문제)', '5'): 3,        # 규정 준수 보고서 위치 → 클라우드용 Microsoft Defender → 4번 (index=3)
    # 3-1 비용관리
    ('3-1_비용관리_2부 (7문제)', '2'): 3,           # 비용 추적 → 태그 → 4번 (index=3)
    ('3-1_비용관리_2부 (7문제)', '5'): 2,           # 부서별 비용 담당 확인 → 태그 → 3번 (index=2)
    # 최종 모의고사1
    ('최종 모의고사1 (39문제)', '32'): 2,  # 아키텍처 검토 지원 플랜 → 프로페셔널 다이렉트 (index=2)
    ('최종 모의고사1 (39문제)', '33'): 3,  # Azure Cost Management → 종량제 구독 (index=3), EA 불필요
    # 3-2 거버넌스및규정준수
    ('3-2_거버넌스및규정준수_2부 (5문제)', '1'): 3, # 감사 보고서 위치 → Service Trust Portal → 4번 (index=3)
    ('3-2_거버넌스및규정준수_2부 (5문제)', '3'): 3, # Microsoft 보안 센터 (blank continuation 제거 후 index=3)
    ('3-2_거버넌스및규정준수_2부 (5문제)', '5'): 1, # Azure Arc → 2번 (index=1)
    # 3-3 리소스관리및배포
    ('3-3_리소스관리및배포_2부 (11문제)', '9'): 2,  # 데스크톱 앱 → Azure CLI → 3번 (index=2)
    # 1-2 클라우드서비스이점: IaaS 마이그레이션 후 사라지는 책임
    # DOCX 원본 A="2,5"이나 정답은 물리적보안관리(idx0) + 고장난하드웨어교체(idx4)
    ('1-2_클라우드서비스이점_2부 (13문제)', '4'): [0, 4],
    # 모의고사5번 Q20: IaaS 마이그레이션 후 사라지는 책임
    # DOCX 원본 A="1,3" → [0,2]이나 정답은 고장난하드웨어교체(idx0) + 물리적보안관리(idx2)
    ('모의고사5번 (30문제)', '20'): [0, 2],
}

# yes/no 문장 텍스트 오버라이드: {(파일명 stem, q_seq, statement_index): 새 문장}
# 원문 번역이 모호하거나 잘못된 경우 명확한 문장으로 교체
_YES_NO_STATEMENT_OVERRIDES: dict[tuple[str, str, int], str] = {
    # PaaS 웹앱 OS 제어: "PaaS가 제어를 제공한다"는 표현이 모호 → 사용자 주체로 명확화
    ('최종 모의고사1 (39문제)', '8', 0):
        'Azure에서 웹앱을 호스팅하는 PaaS 솔루션을 사용하면, '
        '사용자는 애플리케이션을 호스팅하는 운영 체제(OS)를 완전히 제어할 수 있습니다.',
    ('모의고사3번 (45문제)', '18', 0):
        'Azure에서 웹앱을 호스팅하는 PaaS 솔루션을 사용하면, '
        '사용자는 애플리케이션을 호스팅하는 운영 체제(OS)를 완전히 제어할 수 있습니다.',
    # 리소스 그룹 권한 상속: "모든 Azure 리소스 그룹이 상속" → "그룹 내 모든 리소스가 상속"으로 정정
    ('최종 모의고사1 (39문제)', '16', 0):
        '리소스 그룹에 권한을 할당하면, 해당 리소스 그룹 안에 있는 모든 리소스가 그 권한을 상속합니다.',
    ('모의고사6번 (30문제)', '25', 2):
        '리소스 그룹에 권한을 할당하면, 해당 리소스 그룹 안에 있는 모든 리소스가 그 권한을 상속합니다.',
}

# yes/no 정답 오버라이드: {(파일명 stem, q_seq, statement_index): '예'|'아니오'}
_YES_NO_OVERRIDES: dict[tuple[str, str, int], str] = {
    ('3-3_리소스관리및배포_2부 (11문제)', '3', 1): '예',      # Linux 웹 브라우저에서 Cloud Shell 접근? → 예 (브라우저 기반)
    ('3-3_리소스관리및배포_2부 (11문제)', '3', 2): '아니오',  # Windows에서만 Azure Portal 접근? → 아니오
    # 1-1 클라우드컴퓨팅
    ('1-1_클라우드컴퓨팅_2부 (32문제)', '2', 1): '예',     # 하이브리드 클라우드로 앱 위치 제어 가능 → 예
    ('1-1_클라우드컴퓨팅_2부 (32문제)', '2', 2): '아니오', # 퍼블릭 클라우드 VM 확장 = CapEx? → 아니오 (OpEx)
    ('1-1_클라우드컴퓨팅_2부 (32문제)', '7', 1): '예',     # 데이터 센터 전기 요금 = OpEx → 예
    ('1-1_클라우드컴퓨팅_2부 (32문제)', '12', 1): '아니오',# 클라우드 공급자 지불 = CapEx? → 아니오 (OpEx)
    ('1-1_클라우드컴퓨팅_2부 (32문제)', '12', 2): '예',    # 사용량 기반 모델 = OpEx → 예
    # 2-1 Azure핵심아키텍처
    ('2-1_Azure핵심아키텍처_2부 (37문제)', '4', 0): '예',      # ARM 템플릿을 Blueprint에 추가 가능? → 예
    ('2-1_Azure핵심아키텍처_2부 (37문제)', '4', 1): '아니오',  # 리소스 그룹에 Blueprint 할당? → 아니오 (구독/관리그룹 수준)
    ('2-1_Azure핵심아키텍처_2부 (37문제)', '6', 0): '예',      # Azure Advisor는 맞춤화된 권장 사항 제공? → 예
    ('2-1_Azure핵심아키텍처_2부 (37문제)', '9', 0): '예',      # 한 계정으로 여러 구독 관리 가능? → 예
    ('2-1_Azure핵심아키텍처_2부 (37문제)', '14', 0): '아니오', # Trust Center = Defender의 일부? → 아니오
    # 2-2 컴퓨팅및네트워크
    ('2-2_컴퓨팅및네트워크_2부 (21문제)', '6', 0): '예',      # ExpressRoute는 BGP 사용? → 예
    ('2-2_컴퓨팅및네트워크_2부 (21문제)', '6', 2): '예',      # 여러 ExpressRoute 회로 구성 가능? → 예
    # 3-4 모니터링
    ('3-4_모니터링_2부 (5문제)', '3', 0): '예',               # Azure Monitor에서 AD 활동 로그 구성 가능? → 예
}


# 연결(매칭) 문제 분리: {(exam_stem, q_seq): [(질문 텍스트, 정답 option index), ...]}
# 원본 DOCX의 드래그&드롭 연결 문제를 개별 객관식 문제로 변환
_MATCH_QUESTION_SPLITS: dict[tuple[str, str], list[tuple[str, int]]] = {
    ('2-4_ID접근보안_2부 (16문제)', '3'): [
        # options: 0=SSO설명, 1=권한부여설명, 2=MFA설명
        ('권한 부여(Authorization)란 무엇입니까?', 1),
        ('MFA(다단계 인증)란 무엇입니까?', 2),
        ('SSO(Single Sign-On)란 무엇입니까?', 0),
    ],
    ('3-2_거버넌스및규정준수_2부 (5문제)', '2'): [
        # 원본 options 중 [2,3,4]만 사용 (기능 설명만, 기능명 labels 제외)
        # filtered: 0=(VM 유형 제한), 1=(비용 센터 식별), 2=(전체 환경 배포)
        ('Azure 태그(Tag)를 사용하면 어떤 기능을 제공합니까?', 1),
        ('Azure 정책(Policy)을 사용하면 어떤 기능을 제공합니까?', 0),
        ('Azure Blueprints를 사용하면 어떤 기능을 제공합니까?', 2),
    ],
    # ('3-3_리소스관리및배포_2부 (11문제)', '8'): _CUSTOM_QUESTION_OVERRIDES로 대체됨
    # 최종 모의고사1 Q23: LOB 가용 영역 수 (옵션 중 '2) 최소 가용 영역 수' 라벨이 보기에 누출됨)
    # 원본 options: [(3)3, 2)최소가용영역수, (1)1, (2)2, (3)3] → filter=[2,3,4] → [(1)1, (2)2, (3)3]
    ('최종 모의고사1 (39문제)', '23'): [
        ('중요한 LOB(기간 업무) 애플리케이션을 Azure 가상 머신에서 고가용성으로 실행하려면 최소 몇 개의 가용 영역(Availability Zone)이 필요합니까?', 1),
    ],
    # 최종 모의고사2 Q12: Azure VM → IaaS, Azure SQL DB → PaaS (옵션 일부 누출/중복)
    # filter=[0,2,3] → [SaaS, IaaS, PaaS]
    ('최종 모의고사2 (40문제)', '12'): [
        ('Azure 가상 컴퓨터(Virtual Machine)는 어떤 클라우드 서비스 모델에 해당합니까?', 1),
        ('Azure SQL 데이터베이스는 어떤 클라우드 서비스 모델에 해당합니까?', 2),
    ],
}

# 연결 문제 분리 시 사용할 옵션 필터: {(exam_stem, q_seq): [사용할 option index 목록]}
# 지정 시 해당 인덱스의 옵션만 사용, 답 index는 필터링 후 기준
_MATCH_QUESTION_OPTION_FILTERS: dict[tuple[str, str], list[int]] = {
    ('3-2_거버넌스및규정준수_2부 (5문제)', '2'): [2, 3, 4],      # 기능 설명만 (기능명 labels 제외)
    ('최종 모의고사1 (39문제)', '23'): [2, 3, 4],               # (1)1, (2)2, (3)3만 표시 (라벨 누출 제거)
    ('최종 모의고사2 (40문제)', '12'): [0, 2, 3],               # SaaS, IaaS, PaaS만 표시 (누출/중복 제거)
}

# 정보성 문제: {(exam_stem, q_seq): 표시할 안내 메시지}
# 선택지 없이 메시지만 표시, 자동으로 정답(+1) 처리
_INFORMATIONAL_OVERRIDES: dict[tuple[str, str], str] = {
    ('3-3_리소스관리및배포_2부 (11문제)', '4'):
        'Azure Cloud Shell 아이콘은 Azure Portal 상단 메뉴바(검색창 오른쪽)에 있습니다.\n'
        '이 문제가 나올 수 있으니 콘솔에서 아이콘 위치를 기억하세요.',
    # 1-2 클라우드서비스이점 Q2: 드래그&드롭 심층 방어 다이어그램 문제 → 정보성 처리
    ('1-2_클라우드서비스이점_2부 (13문제)', '2'):
        '심층 방어(Defense in Depth) 전략은 여러 보안 레이어를 겹쳐 데이터를 보호합니다.\n\n'
        '계층 구조 (외부 → 내부):\n'
        '① 물리적 보안 — 데이터 센터에 대한 물리적 접근 제어\n'
        '② 신원 및 액세스 — 인증/권한 부여 (MFA, RBAC 등)\n'
        '③ 경계 — DDoS 방어, 방화벽\n'
        '④ 네트워크 — 네트워크 세분화, 액세스 제어\n'
        '⑤ 컴퓨팅 — VM 보안, 엔드포인트 보호\n'
        '⑥ 애플리케이션 — 보안 코딩, 취약점 제거\n'
        '⑦ 데이터 — 암호화, 액세스 제어 (가장 핵심)\n\n'
        '이 문제는 드래그&드롭 형식으로, 각 계층을 올바른 위치에 배치하는 문제입니다.',
}

# 밑줄 문제 밑줄 친 텍스트: {orig_num: 밑줄_텍스트}
# "이 질문은 밑줄이 그어진..." 유형 문제에서 어느 부분이 밑줄인지 표시
_UNDERLINE_TEXT: dict[str, str] = {
    '3':  '고가용성을 구성',
    '5':  '프라이빗 클라우드에서',
    '7':  '월별 사용 비용을 지불',
    '16': 'Azure 정책은',
    '26': '리소스 그룹',
    '33': 'Azure Active Directory(Azure AD) 사용자 계정을 만들 수 없습니다',
    '37': '이동할 수 없습니다',
    '42': '동일한 Azure 지역에 배포해야 합니다',
    '45': '권한 부여',
    '47': '자동으로 삭제됩니다',
    '49': '전역 관리자 그룹의 구성원만 RG1을 삭제할 수 있습니다',
    '53': '모든 Azure 고객이 사용할 수 있습니다',
    '55': '귀하의 은행 계좌를 자동으로 환불합니다',
    '58': '수정해야 합니다',
    '59': '독일의 법적 거주자만',
    '64': '고가용성이 플랫폼에 내장되어 있다',
}


def _format_underline_question(question_text: str, orig_num: str) -> str:
    """밑줄이 그어진 문제를 정리하고 밑줄 친 부분을 <u> 태그로 표시."""
    # "이 질문은 밑줄이 그어진 텍스트가 올바른지 평가해야 합니다." 제거
    text = re.sub(
        r'이 질문은 밑줄이 그어진 텍스트가 올바른지 평가해야 합니다\.?\s*',
        '', question_text
    )
    # "지침: ..." 이후 내용 제거
    text = re.split(r'\n?지침[:：]', text)[0].strip()
    # 밑줄 친 텍스트 <u> 태그로 표시
    underline = _UNDERLINE_TEXT.get(orig_num)
    if underline and underline in text:
        text = text.replace(underline, f'<u>{underline}</u>', 1)
    instruction = '지침: 밑줄 친 텍스트를 검토하십시오. 진술이 올바르면 "변경이 필요하지 않음"을 선택하고, 올바르지 않으면 진술을 올바르게 만드는 선택지를 고르십시오.'
    return f'이 문제는 밑줄 친 텍스트가 올바른지 평가하는 문항입니다.\n\n{text}\n\n{instruction}'


# 커스텀 문제 오버라이드: {(exam_stem, q_seq): dict 또는 list[dict]}
# dict: 단일 문제로 대체. list[dict]: 여러 개의 개별 문제로 분리 출력.
# DOCX 파싱 결과를 완전히 대체하여 명확한 형태로 출력
_CUSTOM_QUESTION_OVERRIDES: dict[tuple[str, str], 'dict | list[dict]'] = {
    # 1-2 클라우드서비스이점 Q3: 연결 문제 → 3개 개별 객관식으로 분리
    # 장점: 확장성, 민첩성, 지역 분포 / 답: 확장성-지역분포-민첩성
    ('1-2_클라우드서비스이점_2부 (13문제)', '3'): [
        {
            'question': '변화하는 요구 사항에 따라 리소스를 동적으로 프로비저닝할 수 있는 클라우드 컴퓨팅의 장점은 무엇입니까?',
            'options': ['확장성', '민첩성', '지역 분포'],
            'answer_index': 0,  # 확장성
        },
        {
            'question': '애플리케이션과 데이터를 여러 지역에 배포할 수 있는 클라우드 컴퓨팅의 장점은 무엇입니까?',
            'options': ['확장성', '민첩성', '지역 분포'],
            'answer_index': 2,  # 지역 분포
        },
        {
            'question': '애플리케이션을 신속하게 개발, 테스트 및 시작할 수 있도록 지원하는 클라우드 컴퓨팅의 장점은 무엇입니까?',
            'options': ['확장성', '민첩성', '지역 분포'],
            'answer_index': 1,  # 민첩성
        },
    ],
    # 1-2 클라우드서비스이점 Q8: 연결 문제 → 3개 개별 객관식으로 분리
    # 장점: 재해 복구, 지역 분포, 고가용성, 확장성
    ('1-2_클라우드서비스이점_2부 (13문제)', '8'): [
        {
            'question': '리소스 실패 시에도 지속적인 사용자 경험을 제공하는 클라우드 컴퓨팅의 장점은 무엇입니까?',
            'options': ['재해 복구', '지역 분포', '고가용성', '확장성'],
            'answer_index': 2,  # 고가용성 (hardware failure에도 지속 가동)
        },
        {
            'question': '앱 및 데이터를 사용자와 가까운 지역 데이터 센터에 배포하는 클라우드 컴퓨팅의 장점은 무엇입니까?',
            'options': ['재해 복구', '지역 분포', '고가용성', '확장성'],
            'answer_index': 1,  # 지역 분포
        },
        {
            'question': '가상 머신에 RAM 또는 CPU를 추가하여 컴퓨팅 용량을 동적으로 늘리는 클라우드 컴퓨팅의 장점은 무엇입니까?',
            'options': ['재해 복구', '지역 분포', '고가용성', '확장성'],
            'answer_index': 3,  # 확장성 (수직 크기 조정)
        },
    ],
    # 1-2 클라우드서비스이점 Q10: 연결 문제 → 3개 개별 객관식으로 분리
    # 장점: 재해 복구, 지역 분포, 고가용성, 확장성 / 답: 확장성-고가용성-지역분포
    ('1-2_클라우드서비스이점_2부 (13문제)', '10'): [
        {
            'question': '클라우드에서 앱의 컴퓨팅 용량을 늘릴 수 있는 클라우드 컴퓨팅의 장점은 무엇입니까?',
            'options': ['재해 복구', '지역 분포', '고가용성', '확장성'],
            'answer_index': 3,  # 확장성
        },
        {
            'question': '명백한 가동 중지 시간 없이 지속적인 사용자 경험을 제공하는 클라우드 컴퓨팅의 장점은 무엇입니까?',
            'options': ['재해 복구', '지역 분포', '고가용성', '확장성'],
            'answer_index': 2,  # 고가용성
        },
        {
            'question': '사용자가 있는 모든 지역에 앱을 배포하여 최상의 경험을 제공하는 클라우드 컴퓨팅의 장점은 무엇입니까?',
            'options': ['재해 복구', '지역 분포', '고가용성', '확장성'],
            'answer_index': 1,  # 지역 분포
        },
    ],
    # 193. 리소스 그룹 독자 역할 할당 노드
    # 원본: 노드/설정 섹션 전체가 선택지로 파싱됨 → 개별 노드 이름으로 교체
    ('3-3_리소스관리및배포_2부 (11문제)', '8'): {
        'question': 'Azure Portal에서 리소스 그룹의 사용자에게 독자(Reader) 역할을 할당하려면 어떤 노드를 클릭해야 합니까?',
        'options': ['개요', '활동 로그', '엑세스 제어 (IAM)', '배포', '속성'],
        'answer_index': 2,  # 엑세스 제어 (IAM)
    },
    # 44. 규정 요구 사항 평가 도구: "Security Center 블레이드" → 현재 명칭 Microsoft Defender for Cloud로 변경
    ('최종 모의고사1 (39문제)', '35'): {
        'question': '회사의 Azure 환경이 규정 요구 사항을 충족하는지 평가하려면 무엇을 사용해야 합니까?',
        'options': [
            'Service Trust Portal의 규정 준수 관리자',
            'Azure 정책의 Advisor 블레이드',
            '지식 센터 웹 사이트',
            'Microsoft Defender for Cloud',
        ],
        'answer_index': 3,  # Microsoft Defender for Cloud (구 Azure Security Center)
    },
    # 21. Azure Government → Azure China 문제로 교체
    # (Azure Government는 미국 전용 서비스라 시험 범위 밖, Azure China 개념이 더 핵심)
    ('최종 모의고사1 (39문제)', '6'): {
        'question': 'Azure China에 대한 설명으로 올바른 것은 무엇입니까?',
        'options': [
            'Microsoft에서 직접 운영합니다.',
            'Azure 글로벌과 동일한 기능 패리티를 제공합니다.',
            '중국에서만 서비스에 액세스할 수 있습니다.',
            'Microsoft Azure의 고유한 별도 인스턴스입니다.',
        ],
        'answer_index': 3,  # Microsoft Azure의 고유한 별도 인스턴스 (21Vianet이 운영)
    },
    ('모의고사6번 (30문제)', '8'): {
        'question': 'Azure China에 대한 설명으로 올바른 것은 무엇입니까?',
        'options': [
            'Microsoft에서 직접 운영합니다.',
            'Azure 글로벌과 동일한 기능 패리티를 제공합니다.',
            '중국에서만 서비스에 액세스할 수 있습니다.',
            'Microsoft Azure의 고유한 별도 인스턴스입니다.',
        ],
        'answer_index': 3,  # Microsoft Azure의 고유한 별도 인스턴스 (21Vianet이 운영)
    },

    # 1-3 클라우드서비스유형 Q4 / 모의고사1번 Q23: "SQL Server 예는 ___" 문장이 선택지 1번으로
    # 잘못 파싱되어 번호가 밀림 → 문제+선택지 완전 재정의 (정답: PaaS)
    ('1-3_클라우드서비스유형_2부 (10문제)', '2'): {
        'question': '설명을 완성하는 답을 선택하십시오.\n클라우드에서 호스팅되고 Azure에서 소프트웨어 업데이트를 관리하는 Microsoft SQL Server 데이터베이스의 예는 무엇입니까?',
        'options': [
            'DRaaS(Disaster Recovery as a Service)입니다.',
            'IaaS(Infrastructure as a Service)입니다.',
            'PaaS(Platform as a Service)입니다.',
            'SaaS(Software as a Service)입니다.',
        ],
        'answer_index': 2,  # PaaS — Azure가 업데이트를 관리하면 PaaS
    },
    ('모의고사1번 (30문제)', '23'): {
        'question': '설명을 완성하는 답을 선택하십시오.\n클라우드에서 호스팅되고 Azure에서 소프트웨어 업데이트를 관리하는 Microsoft SQL Server 데이터베이스의 예는 무엇입니까?',
        'options': [
            'DRaaS(Disaster Recovery as a Service)입니다.',
            'IaaS(Infrastructure as a Service)입니다.',
            'PaaS(Platform as a Service)입니다.',
            'SaaS(Software as a Service)입니다.',
        ],
        'answer_index': 2,  # PaaS — Azure가 업데이트를 관리하면 PaaS
    },

    # ── 최종 모의고사2 용어 현행화 ────────────────────────────────
    # Q5: "Azure 보안 센터" → "Microsoft Defender for Cloud" (distractor 교체, 정답=키 자격 증명 모음)
    ('최종 모의고사2 (40문제)', '5'): {
        'question': '인증서를 저장하려면 어떤 Azure 서비스를 사용해야 합니까?',
        'options': [
            'Microsoft Defender for Cloud',
            'Azure 저장소 계정',
            'Azure 키 자격 증명 모음',
            'Azure 정보 보호',
        ],
        'answer_index': 2,  # Azure 키 자격 증명 모음
    },
    # Q10: "Azure 보안 센터" → "Microsoft Defender for Cloud" (distractor 교체, 정답=키 자격 증명 모음)
    ('최종 모의고사2 (40문제)', '10'): {
        'question': '귀사는 Azure에 대한 서버 배포를 자동화할 계획입니다. 관리자는 배포 중에 관리 자격 증명이 노출될 수 있다고 우려합니다. 배포 중에 관리 자격 증명을 암호화하는 Azure 솔루션을 권장해야 합니다. 추천 내용에 무엇을 포함해야 합니까?',
        'options': [
            'Azure 키 자격 증명 모음',
            'Azure MFA(다단계 인증)',
            'Microsoft Defender for Cloud',
            'Azure 정보 보호',
        ],
        'answer_index': 0,  # Azure 키 자격 증명 모음
    },
    # Q18: "Azure AD(Azure Active Directory) 디렉터리" → "Microsoft Entra ID 디렉터리" (multi_select)
    ('최종 모의고사2 (40문제)', '18'): {
        'question': '회사에서 Azure로 마이그레이션할 계획입니다. 회사에는 여러 부서가 있으며 각 부서에서 사용하는 모든 Azure 리소스는 부서 관리자가 관리합니다. 부서별로 Azure를 분할할 수 있는 기능을 제공하는 Azure 배포를 권장해야 합니다. 솔루션은 관리 노력을 최소화해야 합니다. 추천 내용에 무엇을 포함해야 합니까? 두 개를 선택하십시오.',
        'options': [
            '여러 구독',
            '여러 Microsoft Entra ID 디렉터리',
            '여러 지역',
            '여러 리소스 그룹',
        ],
        'answer_indices': [0, 3],  # 여러 구독, 여러 리소스 그룹
    },
    # Q26: "Azure SQL 데이터 웨어하우스" → "Azure Synapse Analytics" (multi_select)
    ('최종 모의고사2 (40문제)', '26'): {
        'question': 'Azure에 20TB의 데이터를 저장할 계획입니다. 데이터는 드물게 액세스되며 Microsoft Power BI를 사용하여 시각화됩니다. 데이터에 대한 스토리지 솔루션을 권장해야 합니다. 어떤 두 가지 솔루션을 권장해야 합니까?',
        'options': [
            'Azure SQL 데이터베이스',
            'Azure 코스모스 DB',
            'Azure Synapse Analytics',
            'PostgreSQL용 Azure 데이터베이스',
            'Azure 데이터 레이크',
        ],
        'answer_indices': [2, 4],  # Azure Synapse Analytics, Azure 데이터 레이크
    },
    # Q28: "Azure 액티브 디렉터리(Azure AD)" → "Microsoft Entra ID"
    ('최종 모의고사2 (40문제)', '28'): {
        'question': '애플리케이션은 보안 토큰을 검색하기 위해 무엇에 연결해야 합니까?',
        'options': [
            'Azure 저장소 계정',
            'Microsoft Entra ID',
            '인증서 저장소',
            'Azure 키 자격 증명 모음',
        ],
        'answer_index': 1,  # Microsoft Entra ID (구 Azure AD)
    },
    # Q29: "Azure Active Directory(Azure AD)에 동기화" → "Microsoft Entra ID에 동기화"
    ('최종 모의고사2 (40문제)', '29'): {
        'question': '네트워크에는 Active Directory 포리스트가 포함되어 있습니다. 포리스트에는 5,000개의 사용자 계정이 있습니다. 귀사는 모든 네트워크 리소스를 Azure로 마이그레이션하고 온프레미스 데이터 센터를 폐기할 계획입니다. 계획된 마이그레이션 후 사용자에게 미치는 영향을 최소화하기 위한 솔루션을 권장해야 합니다. 무엇을 추천해야 합니까?',
        'options': [
            'Azure MFA(Multi-Factor Authentication) 구현',
            '모든 Active Directory 사용자 계정을 Microsoft Entra ID에 동기화',
            '모든 사용자에게 비밀번호를 변경하도록 지시',
            '각 사용자에 대해 Microsoft Entra ID에서 게스트 사용자 계정 만들기',
        ],
        'answer_index': 1,  # Microsoft Entra ID 동기화 (구 Azure AD)
    },
    # Q33: 질문 오타 "종 소유 비용" → "총 소유 비용" 수정
    ('최종 모의고사2 (40문제)', '33'): {
        'question': 'Azure TCO(총 소유 비용) 계산기를 사용할 수 있는 사람은 누구입니까?',
        'options': [
            'Azure 구독의 소유자만',
            'Azure 구독의 청구 리더만',
            'Azure 구독에만 연결된 Azure AD에 계정이 있는 모든 사용자',
            '모든 사람',
        ],
        'answer_index': 3,  # 모든 사람 (TCO 계산기는 로그인 없이 누구나 사용 가능)
    },
}


def parse_multiple_choice_question(q_seq: str, orig_num: str, content_lines: list[str], a_text: str, exam_stem: str = '') -> 'dict | list[dict]':
    """Parse a multiple choice question. Returns list if split into multiple questions."""

    question_text, options = extract_options_from_mc_text(content_lines)

    # Apply corrections
    question_text = clean_text(question_text)
    options = [clean_text(o) for o in options]

    # 밑줄 문제 자동 포맷: 【밑줄 친 부분】 표시 및 지침 텍스트 정리
    if '밑줄이 그어진 텍스트가 올바른지' in question_text:
        question_text = _format_underline_question(question_text, orig_num)

    # 커스텀 문제 오버라이드: DOCX 파싱 결과를 완전히 대체
    if exam_stem:
        custom = _CUSTOM_QUESTION_OVERRIDES.get((exam_stem, q_seq))
        if custom is not None:
            # list[dict]: 여러 개의 개별 문제로 분리
            if isinstance(custom, list):
                result = []
                for entry in custom:
                    opts = entry['options']
                    ans_indices = entry.get('answer_indices')
                    ans_idx = entry.get('answer_index')
                    if ans_indices:
                        result.append({
                            'id': f'q{q_seq}',
                            'original_num': orig_num,
                            'type': 'multi_select',
                            'question': clean_text(entry['question']),
                            'statements': [],
                            'options': opts,
                            'answer': [],
                            'answer_index': None,
                            'answer_indices': ans_indices,
                            'answer_text': ', '.join(opts[i] for i in ans_indices if i < len(opts)),
                        })
                    else:
                        result.append({
                            'id': f'q{q_seq}',
                            'original_num': orig_num,
                            'type': 'multiple_choice',
                            'question': clean_text(entry['question']),
                            'statements': [],
                            'options': opts,
                            'answer': [],
                            'answer_index': ans_idx,
                            'answer_indices': None,
                            'answer_text': opts[ans_idx] if ans_idx is not None and ans_idx < len(opts) else None,
                        })
                return result
            # dict: 단일 문제로 대체
            opts = custom['options']
            ans_indices = custom.get('answer_indices')
            ans_idx = custom.get('answer_index')
            if ans_indices:
                return [{
                    'id': f'q{q_seq}',
                    'original_num': orig_num,
                    'type': 'multi_select',
                    'question': custom['question'],
                    'statements': [],
                    'options': opts,
                    'answer': [],
                    'answer_index': None,
                    'answer_indices': ans_indices,
                    'answer_text': ', '.join(opts[i] for i in ans_indices if i < len(opts)),
                }]
            else:
                return [{
                    'id': f'q{q_seq}',
                    'original_num': orig_num,
                    'type': 'multiple_choice',
                    'question': custom['question'],
                    'statements': [],
                    'options': opts,
                    'answer': [],
                    'answer_index': ans_idx,
                    'answer_indices': None,
                    'answer_text': opts[ans_idx] if ans_idx is not None and ans_idx < len(opts) else None,
                }]

    # 정보성 문제: 선택지 없이 안내 메시지만 표시
    if exam_stem:
        info_msg = _INFORMATIONAL_OVERRIDES.get((exam_stem, q_seq))
        if info_msg is not None:
            return [{
                'id': f'q{q_seq}',
                'original_num': orig_num,
                'type': 'informational',
                'question': info_msg,
                'statements': [],
                'options': [],
                'answer': [],
                'answer_index': None,
                'answer_indices': None,
                'answer_text': None,
            }]

    # 연결 문제 분리: 여러 개의 개별 객관식 문제로 반환
    if exam_stem:
        splits = _MATCH_QUESTION_SPLITS.get((exam_stem, q_seq))
        if splits and options:
            option_filter = _MATCH_QUESTION_OPTION_FILTERS.get((exam_stem, q_seq))
            if option_filter:
                display_options = [options[i] for i in option_filter if i < len(options)]
            else:
                display_options = options
            result = []
            for q_text, ans_idx in splits:
                result.append({
                    'id': f'q{q_seq}',
                    'original_num': orig_num,
                    'type': 'multiple_choice',
                    'question': clean_text(q_text),
                    'statements': [],
                    'options': display_options,
                    'answer': [],
                    'answer_index': ans_idx,
                    'answer_indices': None,
                    'answer_text': display_options[ans_idx] if ans_idx < len(display_options) else None,
                })
            return result

    # Parse answer (with override support)
    answer_raw = _ANSWER_OVERRIDES.get((exam_stem, q_seq)) if exam_stem else None
    if answer_raw is None:
        answer_raw = parse_multiple_choice_answer(a_text)

    # Determine type and indices
    if isinstance(answer_raw, list):
        q_type = 'multi_select'
        answer_indices = answer_raw
        answer_idx = answer_raw[0] if answer_raw else None
    else:
        q_type = 'multiple_choice'
        answer_indices = None
        answer_idx = answer_raw

    # Get answer text
    answer_text = None
    if q_type == 'multi_select' and answer_indices and options:
        answer_text = ', '.join(
            options[i] for i in answer_indices if i < len(options)
        )
    elif answer_idx is not None and options and answer_idx < len(options):
        answer_text = options[answer_idx]

    return {
        'id': f'q{q_seq}',
        'original_num': orig_num,
        'type': q_type,
        'question': question_text,
        'statements': [],
        'options': options,
        'answer': [],
        'answer_index': answer_idx,
        'answer_indices': answer_indices,
        'answer_text': answer_text,
    }


def parse_docx_file(filepath: str, exam_stem: str = '') -> dict:
    """
    Parse a DOCX file and return structured data with title and questions.

    Returns:
        {
            'title': '...',
            'question_count': N,
            'questions': [...]
        }
    """
    doc = Document(filepath)
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

    if not paragraphs:
        return {'title': '', 'question_count': 0, 'questions': []}

    # First paragraph is the title
    title = paragraphs[0]

    # Find Q/A pairs
    # Q paragraphs start with 'Q\d+\.'
    # A paragraphs start with 'A.'

    questions = []
    i = 0
    q_index = 0

    while i < len(paragraphs):
        para = paragraphs[i]

        # Check if this is a question paragraph
        if re.match(r'^Q\d+\.', para):
            # Find the next A paragraph
            q_text = para
            a_text = None

            for j in range(i + 1, min(i + 5, len(paragraphs))):
                if paragraphs[j].startswith('A.'):
                    a_text = paragraphs[j][2:].strip()  # Remove 'A.' prefix
                    i = j  # Move past the answer
                    break

            if a_text is not None:
                try:
                    parsed_list = parse_question_paragraph(q_text, a_text, q_index, exam_stem=exam_stem)
                    for parsed in (parsed_list or []):
                        if parsed:
                            parsed['id'] = f'q{q_index + 1}'
                            questions.append(parsed)
                            q_index += 1
                except Exception as e:
                    print(f"Warning: Failed to parse question {q_text[:50]}: {e}")

        i += 1

    return {
        'title': title,
        'question_count': len(questions),
        'questions': questions,
    }


def get_exam_id_from_filename(filename: str) -> str:
    """Convert filename to exam ID (remove .docx extension)."""
    return Path(filename).stem


if __name__ == '__main__':
    # Test parsing
    import json
    test_file = '/Users/nurikim/Documents/스킬잇/01. 강의 교안 자료 /AZ900/분류별_문제집/1-1_클라우드컴퓨팅_2부.docx'
    result = parse_docx_file(test_file)
    print(f"Title: {result['title']}")
    print(f"Questions: {result['question_count']}")
    for q in result['questions']:
        print(f"\n{q['id']} ({q['type']}) - Original: {q['original_num']}")
        print(f"  Q: {q['question'][:80]}")
        if q['type'] == 'yes_no':
            print(f"  Statements: {q['statements']}")
            print(f"  Answer: {q['answer']}")
        else:
            print(f"  Options: {q['options']}")
            print(f"  Answer idx: {q['answer_index']}, text: {q['answer_text']}")
