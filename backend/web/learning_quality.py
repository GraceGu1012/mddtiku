"""Evidence-bound instructional metadata. Exam totals never come from model prose."""
import copy

PERIOD=[2017,2026]

def pending_exam_context():
    # Samples are not a reviewed exam corpus; keep missing verification distinct from zero hits.
    return {'period':PERIOD[:],'syllabus_status':'not_provided','syllabus_nodes':[],
            'verified_questions':[],'fully_reviewed_years':[],
            'status':'not_verified','reason':'尚未提供并确认大纲版本，2017—2026真题尚未完成大纲知识点对照'}

def check_quotes(evidence,lookup):
    if not isinstance(evidence,list) or not evidence:raise ValueError('学习设计缺少来源依据')
    for e in evidence:
        if not isinstance(e,dict):raise ValueError('学习设计引文格式无效')
        r=lookup.get(e.get('source_id'));quote=e.get('quote')
        if not r or not isinstance(quote,str) or len(quote.strip())<4 or quote not in r['text']:raise ValueError('学习设计引文无法逐字匹配原文')

def validate_design(design,kind,options,selected,context,allow_inference=False):
    if not isinstance(design,dict):raise ValueError('缺少learning_design学习设计字段')
    allowed={'outline_node_id','exam_question_ids','objective','misconception','option_explanations'}
    if set(design)!=allowed:raise ValueError('学习设计字段不完整或包含模型自算统计')
    objective=design['objective']
    if not isinstance(objective,str) or not objective.strip() or len(objective)>500:raise ValueError('请提供明确考查目标')
    node_id=design['outline_node_id']
    nodes={n['id']:n for n in context.get('syllabus_nodes',[])}
    if node_id is not None and (not isinstance(node_id,str) or node_id not in nodes):raise ValueError('大纲节点不在已提供范围，不能猜测归属')
    requested=design['exam_question_ids']
    if not isinstance(requested,list) or any(not isinstance(i,str) for i in requested) or len(set(requested))!=len(requested):raise ValueError('真题引用ID无效或重复')
    verified={q['id']:q for q in context.get('verified_questions',[])}
    matches=[]
    for qid in requested:
        q=verified.get(qid)
        if not q or q.get('verified') is not True or node_id is None or q.get('outline_node_id')!=node_id:raise ValueError('真题关联未核验或不属于本条大纲节点')
        if type(q.get('year'))!=int or not PERIOD[0]<=q['year']<=PERIOD[1]:raise ValueError('真题年份不在2017—2026范围')
        if not q.get('paper_id') or not q.get('question_number') or not q.get('source_id') or not q.get('material_id'):raise ValueError('真题关联缺少试卷、题号或出处')
        matches.append(q)
    # Coverage uses all reviewed mappings for the chosen node, not only the subset an LLM selects.
    all_matches=[q for q in verified.values() if node_id is not None and q.get('verified') is True and q.get('outline_node_id')==node_id and type(q.get('year'))==int and PERIOD[0]<=q['year']<=PERIOD[1] and q.get('paper_id') and q.get('question_number') and q.get('source_id') and q.get('material_id')]
    dedup={}
    for q in all_matches:dedup[(q['paper_id'],q['year'],str(q['question_number']))]=q
    matches=list(dedup.values());years=sorted({q['year'] for q in matches})
    fully=sorted({y for y in context.get('fully_reviewed_years',[]) if type(y)==int and PERIOD[0]<=y<=PERIOD[1]})
    status='not_verified'
    if node_id is not None and (fully or matches):status='complete' if fully==list(range(2017,2027)) else 'partial'
    lookup={r['source_id']:r for r in selected}
    misconception=design['misconception']
    if not isinstance(misconception,dict) or set(misconception)!={'basis','summary','evidence'}:raise ValueError('易错点字段不完整')
    basis=misconception['basis']
    if basis not in ['none','source_explicit','design_hypothesis']:raise ValueError('易错依据类别无效')
    if basis=='none':
        if misconception['summary']!='' or misconception['evidence']!=[]:raise ValueError('无依据时不得附加易错结论')
    else:
        if not isinstance(misconception['summary'],str) or not misconception['summary'].strip() or len(misconception['summary'])>1500:raise ValueError('易错点描述不明确')
        if not (allow_inference and basis=='design_hypothesis' and misconception['evidence']==[]):
            check_quotes(misconception['evidence'],lookup)
    explanations=design['option_explanations']
    if not isinstance(explanations,list):raise ValueError('逐项解析格式无效')
    if kind=='card':
        if explanations:raise ValueError('卡片不应有选项解析')
    else:
        if len(explanations)!=len(options):raise ValueError('题目必须逐项解析，不得遗漏选项')
        indices=[]
        for e in explanations:
            if not isinstance(e,dict) or set(e)!={'index','explanation','evidence'}:raise ValueError('选项解析字段无效')
            if type(e['index'])!=int or not isinstance(e['explanation'],str) or not e['explanation'].strip() or len(e['explanation'])>2500:raise ValueError('选项解析无效')
            if not (allow_inference and e['evidence']==[]):check_quotes(e['evidence'],lookup)
            indices.append(e['index'])
        if sorted(indices)!=list(range(len(options))):raise ValueError('选项解析索引重复或缺失')
    return {'schema_version':1,'objective':objective,'outline':copy.deepcopy(nodes.get(node_id)),
            'coverage':{'period':PERIOD[:],'status':status,'question_count':len(matches) if status!='not_verified' else None,
                        'year_count':len(years) if status!='not_verified' else None,'years':years,'fully_reviewed_years':fully,
                        'references':copy.deepcopy(matches),'reason':context.get('reason','') if status!='complete' else ''},
            'misconception':copy.deepcopy(misconception),'option_explanations':copy.deepcopy(explanations)}
