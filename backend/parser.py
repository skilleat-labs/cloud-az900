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

        for i, line in enumerate(lines):
            if found_end_of_question:
                options.append(line)
            elif blank_marker in line:
                question_parts.append(line)
                found_end_of_question = True
            else:
                question_parts.append(line)

        question = '\n'.join(question_parts)
        return question, options

    # "설명을 완성하는" 문제인데 blank_marker가 없는 경우:
    # 두 번째 줄이 완성할 문장(문제 텍스트)이고 나머지가 선택지
    # 예: "설명을 완성하는 답을 선택하십시오.\n회사의 규정 준수 보고서는 다음 위치에서 볼 수 있습니다.\nAzure Advisor\n..."
    if lines and '설명을 완성하는' in lines[0] and len(lines) >= 3:
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
        return [parse_multiple_choice_question(q_seq, orig_num, content_lines, a_text, exam_stem=exam_stem)]  # wrap in list


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
        result.append({
            'id': f'q{q_seq}_{i+1}',
            'original_num': orig_num,
            'type': 'yes_no',
            'question': clean_text(stmt),
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
    ('2-4_ID접근보안_2부 (16문제)', '1'): 2,        # SSO 제공 서비스 → Azure AD → 3번 (index=2)
    ('2-4_ID접근보안_2부 (16문제)', '2'): 2,        # 규정 요구사항 평가 → 클라우드용 Microsoft Defender → 3번 (index=2)
    ('2-4_ID접근보안_2부 (16문제)', '5'): 3,        # 규정 준수 보고서 위치 → 클라우드용 Microsoft Defender → 4번 (index=3)
    # 3-1 비용관리
    ('3-1_비용관리_2부 (7문제)', '2'): 3,           # 비용 추적 → 태그 → 4번 (index=3)
    ('3-1_비용관리_2부 (7문제)', '5'): 2,           # 부서별 비용 담당 확인 → 태그 → 3번 (index=2)
    # 3-2 거버넌스및규정준수
    ('3-2_거버넌스및규정준수_2부 (5문제)', '1'): 3, # 감사 보고서 위치 → Service Trust Portal → 4번 (index=3)
    # 1-2 클라우드서비스이점: IaaS 마이그레이션 후 사라지는 책임
    # DOCX 원본 A="2,5"이나 정답은 물리적보안관리(idx0) + 고장난하드웨어교체(idx4)
    ('1-2_클라우드서비스이점_2부 (13문제)', '4'): [0, 4],
    # 모의고사5번 Q20: IaaS 마이그레이션 후 사라지는 책임
    # DOCX 원본 A="1,3" → [0,2]이나 정답은 고장난하드웨어교체(idx0) + 물리적보안관리(idx2)
    ('모의고사5번 (30문제)', '20'): [0, 2],
}

# yes/no 정답 오버라이드: {(파일명 stem, q_seq, statement_index): '예'|'아니오'}
_YES_NO_OVERRIDES: dict[tuple[str, str, int], str] = {
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


def parse_multiple_choice_question(q_seq: str, orig_num: str, content_lines: list[str], a_text: str, exam_stem: str = '') -> dict:
    """Parse a multiple choice question."""

    question_text, options = extract_options_from_mc_text(content_lines)

    # Apply corrections
    question_text = clean_text(question_text)
    options = [clean_text(o) for o in options]

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
