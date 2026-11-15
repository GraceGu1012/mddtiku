"""Versioned, account-owned full-paper attempts; answers are revealed after submission."""
import hashlib
import secrets
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import Field, StrictInt
from bootstrap import storage_dir, APP
from db import transaction, rows, Json
from learner import Payload, require_learner


class Selection(Payload):
    number: StrictInt
    selected: list[StrictInt] = Field(max_length=10)
    revision: StrictInt = Field(ge=0)


class Submit(Payload):
    revision: StrictInt = Field(ge=0)


def paper(cur, pid):
    cur.execute('SELECT * FROM exam_papers WHERE id=%s FOR SHARE', (pid,))
    p = cur.fetchone()
    if not p:raise HTTPException(404, '试卷不存在')
    if p['review_status'] != 'approved':raise HTTPException(403, '该年度尚未开放作答')
    return p


def owned(cur, sid, learner):
    cur.execute('SELECT * FROM exam_paper_sessions WHERE id=%s AND learner_id=%s FOR UPDATE', (sid, learner))
    s = cur.fetchone()
    if not s:raise HTTPException(404, '作答记录不存在')
    p = paper(cur, s['paper_id'])
    if not s['submitted_at'] and p['content_sha256'] != s['content_sha256']:
        raise HTTPException(409, '试卷已更新，请返回年度目录重新开始')
    return s


def public_attempt(s):
    questions = []
    for q in s['snapshot']['questions']:
        clean = {k:q[k] for k in ('number','kind','prompt','options','shared_stem','section','source_pages') if k in q}
        clean['figures'] = [{'url':f"/api/learn/exam-attempts/{s['id']}/figures/{q['number']}/{i}",
                             'alt':f.get('alt', '原题附图')} for i,f in enumerate(q.get('figures', []))]
        clean['selected'] = s['answers'].get(str(q['number']), [])
        if s['submitted_at']:
            expected = sorted(ord(letter)-65 for letter in q.get('answer', []))
            eligible = q.get('answer_status') == 'candidate' and bool(expected)
            clean['correct'] = clean['selected'] == expected if eligible else None
            clean['solution'] = {k:q.get(k) for k in ('answer','explanation','resolution_note','evidence','knowledge_points','cards')}
        questions.append(clean)
    return {k:s[k] for k in ('id','paper_id','title','revision','created_at','submitted_at','result')} | {'questions':questions}


def build_router():
    router = APIRouter(prefix='/api/learn')

    @router.get('/exam-attempts')
    def history(request: Request, paper_id: str):
        return rows('''SELECT id,paper_id,title,revision,created_at,submitted_at,result,
                    jsonb_array_length(snapshot->'questions') AS total,
                    (SELECT count(*) FROM jsonb_each(answers) a WHERE jsonb_array_length(a.value)>0) AS answered
                    FROM exam_paper_sessions WHERE learner_id=%s AND paper_id=%s ORDER BY created_at DESC LIMIT 30''',
                    (require_learner(request), paper_id))

    @router.post('/exam-papers/{pid}/start')
    def start(pid: str, body: Payload, request: Request):
        learner = require_learner(request)
        with transaction() as cur:
            # Serializes double taps across devices without creating duplicate open attempts.
            cur.execute('SELECT id FROM learners WHERE id=%s FOR UPDATE', (learner,))
            p = paper(cur, pid)
            cur.execute('SELECT id FROM exam_paper_sessions WHERE learner_id=%s AND paper_id=%s AND content_sha256=%s AND submitted_at IS NULL',
                        (learner, pid, p['content_sha256']))
            old = cur.fetchone()
            if old:return {'id':old['id']}
            cur.execute('SELECT payload,review_status FROM exam_questions WHERE paper_id=%s ORDER BY number FOR SHARE', (pid,))
            questions = cur.fetchall()
            if not questions or any(q['review_status'] != 'approved' for q in questions):
                raise HTTPException(403, '该套卷题目尚未全部审核')
            sid = secrets.token_hex(16)
            snapshot = {'questions':[q['payload'] for q in questions], 'source_files':p['source_files']}
            cur.execute('INSERT INTO exam_paper_sessions(id,learner_id,paper_id,content_sha256,title,snapshot) VALUES(%s,%s,%s,%s,%s,%s)',
                        (sid,learner,pid,p['content_sha256'],p['title'],Json(snapshot)))
            return {'id':sid}

    @router.get('/exam-attempts/{sid}')
    def get(sid: str, request: Request):
        with transaction() as cur:return public_attempt(owned(cur, sid, require_learner(request)))

    @router.post('/exam-attempts/{sid}/answer')
    def save(sid: str, body: Selection, request: Request):
        with transaction() as cur:
            s = owned(cur, sid, require_learner(request))
            if s['submitted_at']:raise HTTPException(409, '已交卷，不能修改答案')
            if s['revision'] != body.revision:raise HTTPException(409, '进度已变化，请刷新后继续')
            q = next((q for q in s['snapshot']['questions'] if q['number'] == body.number), None)
            if not q:raise HTTPException(422, '题号无效')
            selected = sorted(body.selected)
            if len(selected) != len(set(selected)) or any(n < 0 or n >= len(q['options']) for n in selected):
                raise HTTPException(422, '选项无效')
            if q['kind'] == 'single_choice' and len(selected) > 1:raise HTTPException(422, '单选题只能选一项')
            s['answers'][str(q['number'])] = selected
            cur.execute('UPDATE exam_paper_sessions SET answers=%s,revision=revision+1,updated_at=now() WHERE id=%s', (Json(s['answers']), sid))
            return {'revision':s['revision']+1}

    @router.post('/exam-attempts/{sid}/submit')
    def submit(sid: str, body: Submit, request: Request):
        with transaction() as cur:
            s = owned(cur, sid, require_learner(request))
            if s['submitted_at']:return public_attempt(s)
            if s['revision'] != body.revision:raise HTTPException(409, '进度已变化，请刷新后再交卷')
            result = {'correct':0, 'total':0, 'unresolved':0, 'unanswered':0, 'answered':0}
            for q in s['snapshot']['questions']:
                selected = s['answers'].get(str(q['number']), [])
                result['answered' if selected else 'unanswered'] += 1
                expected = sorted(ord(letter)-65 for letter in q.get('answer', []))
                if q.get('answer_status') != 'candidate' or not expected:result['unresolved'] += 1
                else:
                    result['total'] += 1
                    result['correct'] += int(selected == expected)
            cur.execute('UPDATE exam_paper_sessions SET result=%s,submitted_at=now(),updated_at=now() WHERE id=%s RETURNING *', (Json(result),sid))
            return public_attempt(cur.fetchone())

    @router.get('/exam-attempts/{sid}/figures/{number}/{index}')
    def figure(sid: str, number: int, index: int, request: Request):
        with transaction() as cur:s = owned(cur, sid, require_learner(request))
        q = next((q for q in s['snapshot']['questions'] if q['number'] == number), None)
        figures = q.get('figures', []) if q else []
        if index < 0 or index >= len(figures):raise HTTPException(404, '附图不存在')
        ref = figures[index];info = s['snapshot']['source_files'].get(ref['path'])
        if not info or info['suffix'] != '.png' or info['sha256'] != ref['sha256']:raise HTTPException(404, '附图不存在')
        file = storage_dir() / 'exam-sources' / (info['sha256'] + '.png')
        if not file.is_file():
            # 回退：镜像内打包的附图资产（云托管容器 storage 为空，图随代码库分发）
            file = APP / 'web' / 'exam_assets' / 'exam-sources' / (info['sha256'] + '.png')
        if not file.is_file():raise HTTPException(404, '附图副本不存在')
        if hashlib.sha256(file.read_bytes()).hexdigest() != info['sha256']:raise HTTPException(409, '附图校验失败')
        return FileResponse(file, media_type='image/png', headers={'Cache-Control':'private, no-store'})

    return router
