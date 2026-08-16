"""
explanation.py - DB에 저장된 해설을 읽어오기만 한다.
실제 해설 생성은 generate_explanations.py 스크립트로 사전에 수행한다.
"""

from . import database


async def get_explanation(exam_id: str, question_id: str) -> str | None:
    """DB에서 해설을 가져온다. 없으면 None 반환."""
    return await database.get_explanation(exam_id, question_id)
