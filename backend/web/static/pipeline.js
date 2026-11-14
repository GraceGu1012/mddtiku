/* Material workbench: asynchronous updates never replace the configuration form. */
let pipelineMaterialId = '';
async function pipelinePage() {
  let alive = true, poll, material, preview, selectedJob = '', offset = 0, previewRequest = 0, historyRequest = 0, rangeBusy = false;
  window.pipelineCleanup = () => { alive = false; clearTimeout(poll); };
  const active = () => alive && view === 'materials';
  const error = e => { clearTimeout(poll); if(active()) toast(e.message); };
  const states = {pending:'等待执行',running:'执行中',completed:'已完成',failed:'失败',skipped:'未产出',queued:'排队中'};
  const stages = {analysis:'解析分析 Agent',knowledge:'关键知识点 Agent',generation:'出题 Agent'};
  const usable = boot.models.filter(m=>m.enabled && m.key_configured);
  $('#app').innerHTML = title('材料工作台','上传材料、核对解析、提取知识点和生成内容，在同一处跟进。') + `
    <ol class="pipeline-track"><li>1 人工上传</li><li>2 解析分析 Agent</li><li>3 关键知识点 Agent</li><li>4 出题 Agent</li></ol>
    <section class="panel"><h2>上传材料</h2><div class="actions"><input id="pipeline-files" type="file" multiple accept=".csv,.pdf,.docx" aria-label="选择材料"><button id="pipeline-upload" class="primary">上传并解析</button><span class="muted">CSV / PDF / DOCX · 每份 ≤ 500MB</span></div><div id="pipeline-uploads" aria-live="polite"></div></section>
    <div class="pipeline-layout"><aside class="panel pipeline-materials"><h2>材料</h2><div id="pipeline-material-list"></div></aside><div>
    <section class="panel"><h2 id="pipeline-material-title">选择材料</h2><div id="pipeline-parse-status" aria-live="polite"></div><form id="pipeline-form">
      <div class="row"><label class="field">独立课时<select name="course" id="pipeline-course"><option value="">不适用</option></select></label><label class="field">本次使用模型<select name="model_id" required><option value="">请选择模型</option>${usable.map(m=>`<option value="${esc(m.id)}">${esc(m.name)} · ${esc(m.model)} · v${m.version}</option>`).join('')}</select></label></div>
      <p class="muted" id="pipeline-range-label">CSV 按课时选字幕；PDF 按页；DOCX 按块。</p><div class="row"><label class="field">起始位置<input name="start" type="number" min="1" value="1" required></label><label class="field">结束位置<input name="end" type="number" min="1" value="20" required></label></div>
      <div class="actions"><button type="button" id="pipeline-preview">预览所选范围</button><button type="button" id="pipeline-confirm">确认解析结果</button></div><div id="pipeline-preview-content"></div>
      <details id="pipeline-config" open><summary>生成配置</summary><div class="row"><label class="field">知识卡数量<input name="cards" type="number" min="0" max="20" value="5" required></label><label class="field">题目数量<input name="questions" type="number" min="0" max="20" value="5" required></label></div>
      <div class="row"><label class="field">题型<select name="question_type"><option value="single_choice">单选</option><option value="multiple_choice">多选</option><option value="true_false">判断</option></select></label><label class="field">答案方式<select name="answer_mode"><option value="allow_inference">允许 AI 推理补全</option><option value="source_only">仅依据原文答案</option></select></label></div>
      <p class="muted">每批最多20条、原文范围最多30,000字，预留4次调用。每日总上限 ${boot.settings.value.daily_call_limit} 次。出题提示词 v${boot.prompt.id} · <a href="#settings/prompts">管理出题模板</a></p>
      <p class="muted">AI 推理须明确标注并逐条人工核验；2017—2026 真题统计不可编造。材料内容不作为 Agent 指令执行。</p></details>
      <button id="pipeline-submit" class="primary">开始分析并生成</button><p id="pipeline-gate" class="muted"></p></form></section>
      <section class="panel"><h2>Agent 提示词</h2><details id="pipeline-prompts"><summary>配置分析与知识点模板 / 查看版本历史</summary><div id="pipeline-prompt-content">展开后加载</div></details></section>
      <section class="panel"><div class="actions"><h2>执行详情</h2><button id="pipeline-refresh">刷新状态</button></div><div id="pipeline-job" aria-live="polite"><p class="muted">提交新流程或从下方历史中选择一条记录。</p></div></section>
      <section class="panel"><h2>当前材料的执行历史</h2><div id="pipeline-history"></div><div class="actions"><button id="pipeline-prev">上一页</button><span id="pipeline-page" class="muted"></span><button id="pipeline-next">下一页</button></div></section>
    </div></div>`;
  const form = $('#pipeline-form'), field = name => form.elements.namedItem(name);
  field('model_id').value = usable.some(m=>m.id===selectedModelId)?selectedModelId:usable[0]?.id||'';
  function gate() {
    const reason = !material?'请先上传或选择材料。':material.parse_state!=='parsed'?'材料正在等待解析，解析成功后可继续。':!material.confirmed?'请先核对原文并确认解析结果。':!usable.length?'请先在模型与提示词中配置可用模型。':boot.settings.value.daily_call_limit<4?'每日调用上限不足4次，请先调整配置。':'';
    $('#pipeline-gate').textContent=reason; $('#pipeline-submit').disabled=!!reason||rangeBusy;
    for(const name of ['course','start','end'])field(name).disabled=rangeBusy||!material||material.parse_state!=='parsed';
    $('#pipeline-confirm').disabled=rangeBusy;
    $('#pipeline-confirm').disabled=rangeBusy||!material || material.parse_state!=='parsed' || !!material.confirmed;
    $('#pipeline-preview').disabled=rangeBusy||!material || material.parse_state!=='parsed';
  }
  function renderMaterials(){
    $('#pipeline-material-list').innerHTML=materials.length?materials.map(m=>`<button class="pipeline-material ${m.id===material?.id?'active':''}" data-material="${esc(m.id)}"><strong>${esc(m.name)}</strong><span>${esc(names[m.parse_state]||m.parse_state)} · ${m.confirmed?'已确认':'待确认'}</span></button>`).join(''):'<p class="muted">暂无材料，请先上传。</p>';
    document.querySelectorAll('[data-material]').forEach(b=>b.onclick=()=>selectMaterial(b.dataset.material).catch(error));
  }
  function parseStatus(){
    $('#pipeline-material-title').textContent=material?.name||'选择材料';
    $('#pipeline-parse-status').innerHTML=material?`${badge(material.parse_state)} <span class="muted">${material.confirmed?'已确认解析':'待人工确认'}</span> <a href="/api/materials/${encodeURIComponent(material.id)}/file" target="_blank" rel="noopener">查看原文件</a>${material.error?`<p>${esc(material.error)}</p>`:''}${material.parse_state==='failed'?'<button id="pipeline-parse-retry" type="button">重试本地解析</button>':''}`:'';
    if($('#pipeline-parse-retry'))$('#pipeline-parse-retry').onclick=async()=>{try{await api('materials/'+material.id+'/retry',{});material.parse_state='uploaded';parseStatus();gate();schedule();}catch(e){error(e)}};
    gate();
  }
  async function loadPreview(reset=false,courseChanged=false){
    if(!material || material.parse_state!=='parsed')return;
    const id=material.id, request=++previewRequest;
    const start=reset?1:Number(field('start').value),end=Number(field('end').value);
    if(!reset&&(!Number.isInteger(start)||start<1||!Number.isInteger(end)||end<start))return toast('请选择有效的起始与结束位置');
    const params=new URLSearchParams({course:field('course').value,start:String(start),limit:String(reset||courseChanged?20:Math.min(20,end-start+1))});
    rangeBusy=true;gate();
    let d;try{d=await api(`materials/${id}/preview?${params}`);}finally{if(active()&&request===previewRequest){rangeBusy=false;gate();}}
    if(!active()||material.id!==id||request!==previewRequest)return;
    preview=d;
    if(courseChanged)field('end').value=Math.min(20,d.total)||1;
    if(reset){field('course').innerHTML='<option value="">'+(d.courses.length?'请选择课时':'不适用')+'</option>'+d.courses.map(c=>`<option>${esc(c)}</option>`).join('');field('start').value=1;field('end').value=Math.min(20,d.total)||1;}
    $('#pipeline-range-label').textContent=`${d.type==='pdf'?'按页':d.type==='csv'?'按独立课时的字幕':'按内容块'}选择 · 共 ${d.total} 个来源片段`;
    $('#pipeline-preview-content').innerHTML=`<details open><summary>原文预览（本次最多展示20个片段）</summary>${d.chunks.map(c=>`<div class="source-block"><a href="#source/${id}/${encodeURIComponent(c.source_id)}" target="_blank" rel="noopener">${esc(c.label)}</a><p>${esc(c.text)}</p></div>`).join('')||'<p>此范围没有内容。</p>'}<p class="muted">${esc((d.limitations||[]).join('；'))}${d.issues?.length?' · 解析异常 '+d.issues.length+' 项，请核对原文件。':''}</p></details>`;
  }
  async function historyPage(){
    if(!material){$('#pipeline-history').innerHTML='<p class="muted">选择材料后查看历史。</p>';$('#pipeline-prev').disabled=true;$('#pipeline-next').disabled=true;$('#pipeline-page').textContent='';return;}
    const id=material.id, request=++historyRequest;
    const d=await api(`materials/${id}/history?offset=${offset}&limit=20`);
    if(!active()||material.id!==id||request!==historyRequest)return;
    $('#pipeline-history').innerHTML=d.jobs.length?d.jobs.map((j,i)=>`<button class="pipeline-history-row" data-history="${i}"><span>${esc(j.kind==='pipeline'?'完整 Agent 流程':j.kind==='parse'?'历史本地解析':'历史直接生成')} · ${esc(states[j.state]||j.state)}</span><span class="muted">${esc(formatTime(j.created_at))}</span></button>`).join(''):'<p class="muted">暂无执行记录。</p>';
    $('#pipeline-page').textContent=`共 ${d.total} 条 · 第 ${Math.floor(offset/20)+1} 页`;
    $('#pipeline-prev').disabled=offset===0;$('#pipeline-next').disabled=offset+20>=d.total;
    document.querySelectorAll('[data-history]').forEach(b=>b.onclick=()=>{const j=d.jobs[Number(b.dataset.history)];clearTimeout(poll);selectedJob=j.kind==='pipeline'?j.id:'';if(selectedJob)jobDetail().catch(error);else{renderJob(j);schedule();}});
  }
  function stageResult(s,j){
    const r=s.result||{};
    if(s.name==='analysis')return `<p>${esc(r.summary||'尚未产生分析结果')}</p><p class="muted">${esc(r.document_type||'')} ${esc((r.limitations||[]).join('；'))}</p><details><summary>分析所用原文（${(r.sources||[]).length}段）</summary>${(r.sources||[]).map(x=>`<div class="quote"><a href="#source/${encodeURIComponent(j.material_id)}/${encodeURIComponent(x.source_id)}" target="_blank" rel="noopener">${esc(x.label||x.source_id)}</a><p>${esc(x.text)}</p></div>`).join('')}</details>`;
    if(s.name==='knowledge')return `${(r.points||[]).map(x=>`<div class="pipeline-point"><h3>${esc(x.title)}</h3><p>${esc(x.summary)}</p>${(x.evidence||[]).map(e=>`<div class="quote"><a href="#source/${encodeURIComponent(j.material_id)}/${encodeURIComponent(e.source_id)}" target="_blank" rel="noopener">原文依据</a><p>${esc(e.quote)}</p></div>`).join('')}</div>`).join('')}${r.insufficient_reason?`<p class="info warn">未提取足够知识点：${esc(r.insufficient_reason)}</p>`:''}`;
    return `<p>${s.state==='skipped'?'未执行出题，产出 0 条':r.generated!=null?'生成 '+esc(r.generated)+' 条，待人工审核': '等待生成结果'}</p>${r.insufficient_reason?`<p class="info warn">${esc(r.insufficient_reason)}</p>`:''}`;
  }
  function historySummary(j){
    const cfg=j.config||{},profile=cfg.model_profile||{},model=profile.model||cfg.settings?.model;
    const modelLabel=[profile.name,model].filter(Boolean).join(' / ')||'未记录';
    const version=p=>p?.id!=null?'v'+p.id:'未记录';
    const calls=Array.isArray(j.calls)?j.calls:null;
    const number=n=>typeof n==='number'&&Number.isFinite(n)&&n>=0;
    let tokens='未记录',cost='未记录';
    if(calls?.length){
      let total=0,known=0;const costs=new Map();let unknownCost=false;
      for(const c of calls){
        const u=c.usage;let count=null;
        if(number(u?.total_tokens))count=u.total_tokens;
        else if(number(u?.prompt_tokens)&&number(u?.completion_tokens))count=u.prompt_tokens+u.completion_tokens;
        if(count!==null){total+=count;known++;}
        if(c.cost!==null&&c.cost!==undefined&&Number.isFinite(Number(c.cost))&&c.currency)costs.set(c.currency,(costs.get(c.currency)||0)+Number(c.cost));
        else unknownCost=true;
      }
      tokens=known===calls.length?total.toLocaleString('zh-CN'):known?total.toLocaleString('zh-CN')+'（已记录部分，其余未知）':'未知（调用未记录 usage）';
      cost=[...costs].map(([currency,value])=>value.toFixed(6)+' '+currency).join(' + ');
      if(unknownCost)cost=cost?cost+'（已记录部分，其余未知）':'未知（单价或计费数据未记录）';
    }
    return `<p class="muted" data-pipeline-summary>模型：${esc(modelLabel)} · 提示词：分析 ${esc(version(cfg.analysis_prompt))} / 知识点 ${esc(version(cfg.knowledge_prompt))} / 出题 ${esc(version(cfg.prompt))}<br>已记录调用：${calls?calls.length+' 次':'未记录'} · 累计 tokens：${esc(tokens)} · 成本：${esc(cost)}</p>`;
  }
  function renderJob(j){
    $('#pipeline-job').innerHTML=`<p>${badge(j.state)} ${esc(formatTime(j.created_at))}${j.queue_position!=null?' · 队列位置 '+esc(j.queue_position):''}</p>${historySummary(j)}${j.error?`<div class="info warn">${esc(j.error)}</div>`:''}${j.config?.retry_of?'<p class="info">重试流程：沿用原任务成功阶段及模型 / 提示词快照。</p>':''}${(j.steps||[]).map(s=>`<details open><summary>${esc(stages[s.name]||s.name)} · ${esc(states[s.state]||s.state)}</summary>${s.started_at||s.finished_at?`<p class="muted">${s.started_at?'开始：'+esc(formatTime(s.started_at)):''} ${s.finished_at?'完成：'+esc(formatTime(s.finished_at)):''}</p>`:''}${s.error?`<p>${esc(s.error)}</p>`:''}${stageResult(s,j)}</details>`).join('')}${j.result?`<p>结果：${j.result.generated!=null?'生成 '+esc(j.result.generated)+' 条':esc(j.kind==='parse'?'本地解析记录':'执行记录')}</p>${j.result.insufficient_reason?`<p class="info warn">${esc(j.result.insufficient_reason)}</p>`:''}`:''}${(j.items||[]).map(i=>`<details><summary>${esc(names[i.kind]||i.kind)} · ${esc(i.current?.prompt)} · ${esc(names[i.status]||i.status)}</summary><p>${(i.current?.options||[]).map((o,n)=>`${String.fromCharCode(65+n)}. ${esc(o)}`).join('<br>')}</p><p>答案：${esc(i.current?.answer)}</p><p>${esc(i.current?.ai_explanation)}</p><p class="muted">${i.evidence?.answer_origin==='ai_inference'?'AI 推理补全 · 须独立核验':'材料依据答案'}</p><p class="muted">关联知识点：${esc((i.evidence?.knowledge_points||[]).map(p=>p.title).join('、')||'未记录')}</p></details>`).join('')}<details><summary>本次配置快照及调用记录</summary><pre>${esc(JSON.stringify({config:j.config,result:j.result,calls:j.calls||[]},null,2))}</pre></details>${j.kind==='pipeline'||j.steps?.length?'<p><a class="button" href="#review">前往人工审核</a> <span class="muted">生成完成不代表已入库。</span></p>':''}${j.state==='failed'&&selectedJob?'<p class="muted">重试创建新流程，继承已成功的分析 / 知识点；后续模型调用可能产生费用。</p><button id="pipeline-retry">确认重试（可能计费）</button>':''}`;
    if($('#pipeline-retry'))$('#pipeline-retry').onclick=async()=>{if(!confirm('重试将创建新流程，后续模型调用可能计费，是否继续？'))return;const b=$('#pipeline-retry');b.disabled=true;try{const d=await api('pipelines/'+selectedJob+'/retry',{});if(!active())return;selectedJob=d.id;await jobDetail();await historyPage();}catch(e){error(e);if(b.isConnected)b.disabled=false;}};
  }
  async function jobDetail(){
    if(!selectedJob)return;
    const id=selectedJob,d=await api('pipelines/'+id);
    if(!active()||id!==selectedJob)return;
    renderJob({...d,kind:'pipeline'});
    if(['queued','running'].includes(d.state))schedule();
    else {clearTimeout(poll);await historyPage();if(material&&['uploaded','parsing'].includes(material.parse_state))schedule();}
  }
  function schedule(){clearTimeout(poll);if(active())poll=setTimeout(()=>tick().catch(error),2000);}
  async function tick(){
    if(!active())return;
    if(material&&['uploaded','parsing'].includes(material.parse_state)){
      const id=material.id, rows=await api('materials');if(!active()||material.id!==id)return;
      materials=rows;material=rows.find(m=>m.id===id);parseStatus();renderMaterials();
      if(material?.parse_state==='parsed'){await loadPreview(true);await historyPage();}
      if(material&&['uploaded','parsing'].includes(material.parse_state))schedule();
    }
    if(selectedJob)await jobDetail();
  }
  async function selectMaterial(id){clearTimeout(poll);selectedJob='';offset=0;pipelineMaterialId=id;material=materials.find(m=>m.id===id);preview=null;++previewRequest;rangeBusy=false;field('course').innerHTML='<option value="">不适用</option>';$('#pipeline-preview-content').innerHTML='';$('#pipeline-job').innerHTML='<p class="muted">请选择历史记录，或开始新流程。</p>';renderMaterials();parseStatus();await loadPreview(true);await historyPage();if(material&&['uploaded','parsing'].includes(material.parse_state))schedule();}
  $('#pipeline-preview').onclick=()=>loadPreview().catch(error);
  field('course').onchange=()=>{field('start').value=1;loadPreview(false,true).catch(error);};
  $('#pipeline-confirm').onclick=async()=>{const id=material.id;try{await api('materials/'+id+'/confirm',{});if(!active()||material?.id!==id)return;material.confirmed=true;parseStatus();renderMaterials();toast('已确认解析，可以开始分析。');}catch(e){error(e)}};
  $('#pipeline-prev').onclick=()=>{offset=Math.max(0,offset-20);historyPage().catch(error)};
  $('#pipeline-next').onclick=()=>{offset+=20;historyPage().catch(error)};
  $('#pipeline-refresh').onclick=async()=>{try{const id=material?.id, rows=await api('materials');if(!active()||material?.id!==id)return;materials=rows;material=rows.find(m=>m.id===id);parseStatus();renderMaterials();if(selectedJob)await jobDetail();await historyPage();if(material&&['uploaded','parsing'].includes(material.parse_state))schedule();}catch(e){error(e)}};
  form.onsubmit=async e=>{e.preventDefault();if(!material||$('#pipeline-submit').disabled)return;const config=Object.fromEntries(new FormData(form));for(const n of ['start','end','cards','questions'])config[n]=Number(config[n]);if(preview?.courses.length&&!config.course)return toast('请选择一个独立课时');if(config.end<config.start)return toast('结束位置不能小于起始位置');if(config.cards+config.questions<1||config.cards+config.questions>20)return toast('每批总数量需为1至20条');config.material_id=material.id;config.model_version=boot.models.find(m=>m.id===config.model_id)?.version;selectedModelId=config.model_id;$('#pipeline-submit').disabled=true;try{const d=await api('pipelines',config);if(!active()||material?.id!==config.material_id)return;selectedJob=d.id;await jobDetail();offset=0;await historyPage();toast('已提交完整流程，完成后请人工审核。');}catch(e){error(e)}finally{if(active())gate()}};
  $('#pipeline-upload').onclick=async()=>{
    const files=[...$('#pipeline-files').files];if(!files.length)return toast('请先选择文件');const b=$('#pipeline-upload');b.disabled=true;
    $('#pipeline-uploads').innerHTML=files.map((f,i)=>`<div><span>${esc(f.name)}</span><progress id="pipeline-progress-${i}" max="100" value="0"></progress><p id="pipeline-upload-status-${i}" class="muted">等待上传</p></div>`).join('');
    let lastId='';
    for(let i=0;i<files.length;i++){if(!active())break;try{const file=files[i];if(file.size>500*1024*1024)throw Error('文件超过500MB');const result=await new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest(),data=new FormData();data.append('file',file);xhr.open('POST','/api/upload');xhr.setRequestHeader('X-CSRF-Token',boot.csrf);xhr.upload.onprogress=e=>{if(active()&&e.lengthComputable){$('#pipeline-progress-'+i).value=e.loaded/e.total*100;$('#pipeline-upload-status-'+i).textContent='上传 '+Math.round(e.loaded/e.total*100)+'%';}};xhr.onload=()=>{try{const d=JSON.parse(xhr.responseText);if(xhr.status>=400)reject(Error(d.detail||'上传失败'));else resolve(d);}catch(e){reject(e)}};xhr.onerror=()=>reject(Error('上传连接失败'));xhr.send(data);});lastId=result.id||result.material?.id;if(active()){$('#pipeline-progress-'+i).value=100;$('#pipeline-upload-status-'+i).textContent=result.duplicate?'重复文件，已保留原记录':'已上传，等待本地解析';}}catch(e){if(active())$('#pipeline-upload-status-'+i).textContent=e.message;}}
    if(active()){try{materials=await api('materials');if(active()&&lastId)await selectMaterial(lastId);}catch(e){error(e)}b.disabled=false;}
  };
  $('#pipeline-prompts').ontoggle=async()=>{if(!$('#pipeline-prompts').open)return;try{await loadPrompts()}catch(e){error(e)}};
  async function loadPrompts(){const ps=await api('agent-prompts');if(!active())return;$('#pipeline-prompt-content').innerHTML=Object.entries(stages).filter(([s])=>s!=='generation').map(([s,label])=>{const versions=ps.filter(p=>p.stage===s),p=versions[0];return `<form data-prompt-stage="${s}" data-base="${p?.id||''}"><h3>${label} · v${p?.id||'未配置'}</h3><textarea name="content" required aria-label="${label}提示词">${esc(p?.content||'')}</textarea><button>保存新版本</button><details><summary>版本历史（${versions.length}）</summary>${versions.map(v=>`<details><summary>v${v.id} · ${esc(formatTime(v.created_at))}</summary><pre>${esc(v.content)}</pre></details>`).join('')}</details></form>`;}).join('');document.querySelectorAll('[data-prompt-stage]').forEach(f=>f.onsubmit=async e=>{e.preventDefault();f.querySelector('button').disabled=true;try{await api('agent-prompts',{stage:f.dataset.promptStage,base_version:Number(f.dataset.base)||null,content:f.elements.content.value});await loadPrompts();toast('已保存新版本，已有任务快照不变。');}catch(e){error(e);if(f.isConnected)f.querySelector('button').disabled=false;}});}
  await selectMaterial(materials.some(m=>m.id===pipelineMaterialId)?pipelineMaterialId:materials[0]?.id||'');
}
