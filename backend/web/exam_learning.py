"""Read-only annual paper directory; draft questions remain restricted to staff."""
from fastapi import APIRouter, HTTPException, Request
from db import one, rows


def can_preview(request):
    person = getattr(request.state, 'principal', None)
    return bool(person and person.get('role') in ('admin', 'teacher', 'reviewer'))


def summaries(pid=None):
    return rows('''SELECT p.id,p.year,p.title,p.review_status,
        count(q.number)::int AS question_count,
        count(q.number) FILTER(WHERE q.answer_status='candidate')::int AS answered_count,
        count(q.number) FILTER(WHERE q.answer_status<>'candidate')::int AS unresolved_count,
        coalesce(sum(jsonb_array_length(q.payload->'cards')),0)::int AS card_count
        FROM exam_papers p LEFT JOIN exam_questions q ON q.paper_id=p.id
        ''' + ('WHERE p.id=%s ' if pid is not None else '') +
        'GROUP BY p.id ORDER BY p.year DESC,p.id', (pid,) if pid is not None else ())


def build_router():
    router = APIRouter(prefix='/api/learn/exam-papers')

    @router.get('')
    def listing(request: Request):
        return {'papers': summaries(), 'can_preview': can_preview(request)}

    @router.get('/{pid}')
    def detail(pid: str, request: Request):
        found = summaries(pid)
        if not found:raise HTTPException(404, '试卷不存在')
        result = {**found[0], 'can_preview': can_preview(request)}
        if result['can_preview']:
            result['question_numbers'] = [q['number'] for q in rows(
                'SELECT number FROM exam_questions WHERE paper_id=%s ORDER BY number', (pid,))]
        return result

    @router.get('/{pid}/questions/{number}')
    def question(pid: str, number: int, request: Request):
        if not can_preview(request):raise HTTPException(403, '真题尚未开放学习，草稿仅供教研核对')
        item = one('SELECT payload FROM exam_questions WHERE paper_id=%s AND number=%s', (pid, number))
        if not item:raise HTTPException(404, '题目不存在')
        return item['payload']

    return router
