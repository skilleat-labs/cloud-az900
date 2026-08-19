"""
FastAPI main application for AZ-900 Quiz.
"""

import os
import uuid
import random
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from .parser import parse_docx_file, get_exam_id_from_filename
from . import database
from .explanation import get_explanation

app = FastAPI(title="AZ-900 Quiz API", version="1.0.0")

QUESTIONS_DIR = os.getenv(
    'QUESTIONS_DIR',
    str(Path(__file__).parent.parent / 'questions')
)

# In-memory cache for parsed questions
_questions_cache: dict[str, dict] = {}


ALLOWED_FILES = {
    '모의고사1번 (30문제).docx',
    '모의고사2번 (32문제).docx',
    '모의고사3번 (45문제).docx',
    '모의고사4번 (32문제).docx',
    '모의고사5번 (30문제).docx',
    '모의고사6번 (30문제).docx',
    '1-1_클라우드컴퓨팅_2부 (32문제).docx',
    '1-2_클라우드서비스이점_2부 (13문제).docx',
    '1-3_클라우드서비스유형_2부 (10문제).docx',
    '2-1_Azure핵심아키텍처_2부 (37문제).docx',
    '2-2_컴퓨팅및네트워크_2부 (21문제).docx',
    '2-3_스토리지서비스_2부 (11문제).docx',
    '2-4_ID접근보안_2부 (16문제).docx',
    '3-1_비용관리_2부 (7문제).docx',
    '3-2_거버넌스및규정준수_2부 (5문제).docx',
    '3-3_리소스관리및배포_2부 (11문제).docx',
    '3-4_모니터링_2부 (5문제).docx',
}

def get_docx_files() -> list[Path]:
    """Get allowed DOCX files from QUESTIONS_DIR."""
    questions_path = Path(QUESTIONS_DIR)
    if not questions_path.exists():
        return []
    return sorted(f for f in questions_path.glob('*.docx') if f.name in ALLOWED_FILES)


def load_exam(exam_id: str) -> dict | None:
    """Load and cache exam questions."""
    if exam_id in _questions_cache:
        return _questions_cache[exam_id]

    docx_files = get_docx_files()
    for f in docx_files:
        if get_exam_id_from_filename(f.name) == exam_id:
            data = parse_docx_file(str(f), exam_stem=f.stem)
            data['exam_id'] = exam_id
            data['filename'] = f.name
            _questions_cache[exam_id] = data
            return data

    return None


@app.on_event("startup")
async def startup():
    """Initialize database on startup."""
    await database.init_db()

    # Scan and register all exams
    docx_files = get_docx_files()
    for f in docx_files:
        exam_id = get_exam_id_from_filename(f.name)
        try:
            data = load_exam(exam_id)
            if data:
                await database.upsert_exam(
                    exam_id,
                    f.name,
                    data['title'],
                    data['question_count']
                )
        except Exception as e:
            print(f"Warning: Failed to load {f.name}: {e}")


# ─────────────────────────────────────────────
#  API Routes
# ─────────────────────────────────────────────

@app.get("/api/exams")
async def list_exams():
    """List all available exam files."""
    try:
        exams = await database.get_all_exams()
    except Exception as e:
        print(f"Warning: get_all_exams failed ({e}), re-running init_db")
        try:
            await database.init_db()
        except Exception as e2:
            print(f"Warning: init_db also failed ({e2})")
        exams = []

    # Refresh from filesystem if empty
    if not exams:
        docx_files = get_docx_files()
        fs_exams = []
        for f in docx_files:
            exam_id = get_exam_id_from_filename(f.name)
            try:
                data = load_exam(exam_id)
                if data:
                    try:
                        await database.upsert_exam(
                            exam_id, f.name, data['title'], data['question_count']
                        )
                    except Exception:
                        pass
                    fs_exams.append({
                        'id': exam_id,
                        'filename': f.name,
                        'title': data['title'],
                        'question_count': data['question_count'],
                        'created_at': '',
                    })
            except Exception:
                pass
        try:
            exams = await database.get_all_exams()
        except Exception:
            exams = fs_exams  # DB 완전 실패 시 파일시스템 결과 직접 반환

    # ALLOWED_FILES 기준으로 필터링 (삭제된 시험이 DB에 남아 있어도 노출 안 됨)
    exams = [e for e in exams if e['filename'] in ALLOWED_FILES]

    return exams


@app.get("/api/exams/{exam_id}/questions")
async def get_questions(exam_id: str, shuffle: bool = True):
    """Get questions for an exam (without answers)."""
    data = load_exam(exam_id)
    if not data:
        raise HTTPException(status_code=404, detail="Exam not found")

    questions = data['questions'].copy()

    if shuffle:
        random.shuffle(questions)

    # Strip answers before sending to client
    safe_questions = []
    for q in questions:
        safe_q = {
            'id': q['id'],
            'original_num': q['original_num'],
            'type': q['type'],
            'question': q['question'],
            'statements': q.get('statements', []),
            'options': q.get('options', []),
        }
        # Include answer count hint for multi_select so frontend can show "N개 선택"
        if q['type'] == 'multi_select' and q.get('answer_indices'):
            safe_q['answer_count'] = len(q['answer_indices'])
        safe_questions.append(safe_q)

    return {
        'exam_id': exam_id,
        'title': data['title'],
        'questions': safe_questions,
    }


class SessionCreate(BaseModel):
    exam_id: str
    user_name: str


@app.post("/api/sessions")
async def create_session(body: SessionCreate):
    """Create a new quiz session."""
    # Verify exam exists
    data = load_exam(body.exam_id)
    if not data:
        raise HTTPException(status_code=404, detail="Exam not found")

    session_id = str(uuid.uuid4())
    session = await database.create_session(session_id, body.exam_id, body.user_name)
    return session


class AnswerItem(BaseModel):
    question_id: str
    user_answer: list | int | str


class SessionSubmit(BaseModel):
    answers: list[AnswerItem]
    time_seconds: int


@app.post("/api/sessions/{session_id}/submit")
async def submit_session(session_id: str, body: SessionSubmit):
    """Submit answers for a session and compute score."""
    session = await database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.get('finished_at'):
        raise HTTPException(status_code=400, detail="Session already submitted")

    exam_id = session['exam_id']
    data = load_exam(exam_id)
    if not data:
        raise HTTPException(status_code=404, detail="Exam not found")

    # Build answer key lookup
    answer_key = {q['id']: q for q in data['questions']}

    score = 0
    total = len(body.answers)
    processed_answers = []

    for ans in body.answers:
        q_id = ans.question_id
        user_answer = ans.user_answer
        question = answer_key.get(q_id)

        if not question:
            continue

        is_correct = False
        q_type = question.get('type', 'multiple_choice')

        if q_type == 'yes_no':
            correct = question.get('answer', '')
            if isinstance(user_answer, str):
                is_correct = user_answer == correct
            else:
                is_correct = False
        elif q_type == 'multi_select':
            correct_indices = question.get('answer_indices') or []
            if isinstance(user_answer, list):
                is_correct = sorted(user_answer) == sorted(correct_indices)
            else:
                is_correct = False
        else:
            correct_idx = question.get('answer_index')
            if isinstance(user_answer, int):
                is_correct = user_answer == correct_idx
            elif isinstance(user_answer, str) and user_answer.isdigit():
                is_correct = int(user_answer) == correct_idx
            else:
                is_correct = False

        if is_correct:
            score += 1

        processed_answers.append({
            'question_id': q_id,
            'user_answer': user_answer,
            'is_correct': is_correct,
        })

    # Save to DB
    await database.finish_session(
        session_id, score, total, body.time_seconds, processed_answers
    )

    # Build result with question details (explanations from pre-generated DB)
    result_questions = []
    for ans in processed_answers:
        q_id = ans['question_id']
        question = answer_key.get(q_id, {})
        q_type = question.get('type', 'multiple_choice')

        q_result = {
            'question_id': q_id,
            'type': q_type,
            'question': question.get('question', ''),
            'user_answer': ans['user_answer'],
            'is_correct': ans['is_correct'],
        }

        if q_type == 'yes_no':
            q_result['correct_answer'] = question.get('answer', '')
        elif q_type == 'multi_select':
            q_result['options'] = question.get('options', [])
            q_result['correct_answer_indices'] = question.get('answer_indices', [])
            q_result['correct_answer_text'] = question.get('answer_text', '')
        else:
            q_result['options'] = question.get('options', [])
            q_result['correct_answer_index'] = question.get('answer_index')
            q_result['correct_answer_text'] = question.get('answer_text', '')

        if not ans['is_correct']:
            q_result['explanation'] = await get_explanation(exam_id, q_id)

        result_questions.append(q_result)

    return {
        'session_id': session_id,
        'score': score,
        'total': total,
        'time_seconds': body.time_seconds,
        'percentage': round(score / total * 100) if total > 0 else 0,
        'questions': result_questions,
    }


@app.get("/api/sessions/{session_id}/result")
async def get_session_result(session_id: str):
    """Get session result with explanations."""
    session = await database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.get('finished_at'):
        raise HTTPException(status_code=400, detail="Session not yet submitted")

    exam_id = session['exam_id']
    data = load_exam(exam_id)
    answers = await database.get_session_answers(session_id)

    answer_key = {q['id']: q for q in (data['questions'] if data else [])}

    result_questions = []
    for ans in answers:
        q_id = ans['question_id']
        question = answer_key.get(q_id, {})
        q_type = question.get('type', 'multiple_choice')

        q_result = {
            'question_id': q_id,
            'type': q_type,
            'question': question.get('question', ''),
            'user_answer': ans['user_answer'],
            'is_correct': bool(ans['is_correct']),
        }

        if q_type == 'yes_no':
            q_result['correct_answer'] = question.get('answer', '')
        elif q_type == 'multi_select':
            q_result['options'] = question.get('options', [])
            q_result['correct_answer_indices'] = question.get('answer_indices', [])
            q_result['correct_answer_text'] = question.get('answer_text', '')
        else:
            q_result['options'] = question.get('options', [])
            q_result['correct_answer_index'] = question.get('answer_index')
            q_result['correct_answer_text'] = question.get('answer_text', '')

        if not ans['is_correct']:
            explanation = await database.get_explanation(exam_id, q_id)
            if explanation:
                q_result['explanation'] = explanation

        result_questions.append(q_result)

    return {
        'session_id': session_id,
        'exam_id': exam_id,
        'user_name': session['user_name'],
        'score': session['score'],
        'total': session['total'],
        'time_seconds': session['time_seconds'],
        'percentage': round(session['score'] / session['total'] * 100) if session['total'] else 0,
        'started_at': session['started_at'],
        'finished_at': session['finished_at'],
        'questions': result_questions,
    }


@app.get("/api/admin/wrong-stats")
async def get_wrong_stats(exam_id: Optional[str] = None):
    """문제별 오답 통계 + 문제 텍스트 + 해설 반환 (관리자용)."""
    stats = await database.get_wrong_stats(exam_id)

    result = []
    for row in stats:
        eid = row['exam_id']
        qid = row['question_id']

        # 문제 텍스트 로드
        exam_data = load_exam(eid)
        question = next((q for q in (exam_data['questions'] if exam_data else []) if q['id'] == qid), None)

        # 해설 로드
        explanation = await database.get_explanation(eid, qid)

        entry = {
            'exam_id': eid,
            'exam_title': exam_data['title'] if exam_data else eid,
            'question_id': qid,
            'attempts': row['attempts'],
            'wrong_count': row['wrong_count'],
            'wrong_rate': row['wrong_rate'],
        }
        if question:
            entry['type'] = question['type']
            entry['question'] = question['question']
            entry['options'] = question.get('options', [])
            entry['answer'] = question.get('answer', '')
            entry['answer_index'] = question.get('answer_index')
            entry['answer_text'] = question.get('answer_text', '')
        if explanation:
            entry['explanation'] = explanation

        result.append(entry)

    return result


@app.get("/api/leaderboard")
async def get_leaderboard(exam_id: Optional[str] = None):
    """Get leaderboard for an exam."""
    if not exam_id:
        raise HTTPException(status_code=400, detail="exam_id is required")

    entries = await database.get_leaderboard(exam_id, limit=20)

    result = []
    for rank, entry in enumerate(entries, 1):
        percentage = round(entry['score'] / entry['total'] * 100) if entry['total'] else 0
        result.append({
            'rank': rank,
            'user_name': entry['user_name'],
            'score': entry['score'],
            'total': entry['total'],
            'percentage': percentage,
            'time_seconds': entry['time_seconds'],
            'finished_at': entry['finished_at'],
        })

    return result


# ─────────────────────────────────────────────
#  Static files
# ─────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

# Mount static files AFTER API routes
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
