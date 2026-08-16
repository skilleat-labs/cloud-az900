"""
해설 사전 생성 스크립트
사용법: cd /Users/nurikim/Documents/az900-quiz && python -m backend.generate_explanations

- ALLOWED_FILES에 정의된 모든 시험지의 전체 문제 해설을 Claude API로 생성한다.
- 이미 생성된 해설은 건너뛴다 (재실행 안전).
- 생성된 해설은 DB(quiz.db)에 저장된다.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from .parser import parse_docx_file
from .database import init_db, get_explanation, save_explanation
from .main import ALLOWED_FILES, QUESTIONS_DIR

MODEL = "claude-haiku-4-5-20251001"


def get_client():
    from anthropic import Anthropic
    api_key = os.getenv('ANTHROPIC_API_KEY', '')
    if not api_key or api_key == 'your_key_here':
        print("❌ .env 파일에 ANTHROPIC_API_KEY를 설정해주세요.")
        sys.exit(1)
    return Anthropic(api_key=api_key)


def build_prompt(question: dict) -> str:
    q_type = question['type']
    q_text = question['question']

    if q_type == 'yes_no':
        correct = question['answer']  # '예' or '아니오'
        return f"""당신은 Microsoft Azure AZ-900 자격증 시험 전문 강사입니다.
다음 예/아니오 문제에 대해 학생이 이해할 수 있도록 명확한 해설을 한국어로 작성해주세요.

**문제:** {q_text}
**정답:** {correct}

요청 사항:
1. 이 진술이 왜 '{correct}'인지 Azure/AZ-900 공식 개념을 근거로 설명해주세요.
2. 학생들이 흔히 헷갈리는 포인트가 있다면 짚어주세요.
3. 핵심 개념을 한 줄로 요약해주세요.
4. 마크다운(볼드, 리스트)을 사용해 읽기 쉽게 작성하고, 3~5문장으로 간결하게 써주세요."""

    else:  # multiple_choice
        options = question.get('options', [])
        answer_idx = question.get('answer_index', 0)
        options_text = '\n'.join(f"  {i+1}. {opt}" for i, opt in enumerate(options))
        correct_text = options[answer_idx] if answer_idx is not None and answer_idx < len(options) else ''

        return f"""당신은 Microsoft Azure AZ-900 자격증 시험 전문 강사입니다.
다음 객관식 문제에 대해 학생이 이해할 수 있도록 명확한 해설을 한국어로 작성해주세요.

**문제:** {q_text}

**선택지:**
{options_text}

**정답:** {answer_idx + 1 if answer_idx is not None else '?'}번. {correct_text}

요청 사항:
1. 정답이 왜 맞는지 Azure/AZ-900 공식 개념을 근거로 설명해주세요.
2. 오답 선택지가 왜 틀렸는지 간략히 짚어주세요.
3. 핵심 개념을 한 줄로 요약해주세요.
4. 마크다운(볼드, 리스트)을 사용해 읽기 쉽게 작성하고, 4~6문장으로 간결하게 써주세요."""


def generate_one_sync(client, question: dict) -> str:
    prompt = build_prompt(question)
    message = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text


async def run():
    await init_db()
    client = get_client()

    questions_path = Path(QUESTIONS_DIR)
    files = sorted(f for f in questions_path.glob('*.docx') if f.name in ALLOWED_FILES)

    total_questions = 0
    total_generated = 0
    total_skipped = 0

    print(f"\n{'='*55}")
    print(f"  AZ-900 해설 사전 생성 ({len(files)}개 시험지)")
    print(f"{'='*55}\n")

    for file_path in files:
        exam_id = file_path.stem  # 파일명에서 .docx 제거
        data = parse_docx_file(str(file_path))
        questions = data['questions']

        print(f"📄 {file_path.name}  ({len(questions)}문제)")

        for q in questions:
            total_questions += 1
            q_id = q['id']

            # 이미 생성된 해설은 건너뜀
            existing = await get_explanation(exam_id, q_id)
            if existing:
                total_skipped += 1
                print(f"   ⏭  {q_id} 건너뜀 (이미 존재)")
                continue

            # 생성
            try:
                loop = asyncio.get_event_loop()
                explanation = await loop.run_in_executor(
                    None, generate_one_sync, client, q
                )
                await save_explanation(exam_id, q_id, explanation)
                total_generated += 1
                print(f"   ✅ {q_id} 완료")
                time.sleep(0.3)  # rate limit 방지
            except Exception as e:
                print(f"   ❌ {q_id} 오류: {e}")

        print()

    print(f"{'='*55}")
    print(f"  완료: {total_generated}개 생성 / {total_skipped}개 건너뜀 / 총 {total_questions}문제")
    print(f"{'='*55}\n")


if __name__ == '__main__':
    asyncio.run(run())
