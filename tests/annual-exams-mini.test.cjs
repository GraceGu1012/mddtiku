const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const miniRoot = process.env.EXAM_MINI_ROOT || path.join(root, 'miniprogram-cloud');
function page(name, api) {
    let result;
    new Function('Page', 'require', 'wx', fs.readFileSync(path.join(miniRoot, 'pages', name, name + '.js'), 'utf8'))(
        p => result = p, () => ({ api }), { navigateTo() {}, setNavigationBarTitle() {} });
    result.data = structuredClone(result.data);
    result.setData = data => Object.assign(result.data, data);
    return result;
}
test('年度目录按新到旧排列；显示真实统计，不把候选答案当已发布', async () => {
    const p = page('exam-papers', async () => ({ papers: [
        { id: 'old', year: 2017, question_count: 165 }, { id: 'new', year: 2026, question_count: 165 }
    ], can_preview: false }));
    await p.load();
    assert.equal(p.data.state, 'ready');
    assert.deepEqual(p.data.papers.map(x => x.year), [2026, 2017]);
    assert.equal(p.data.total, 330);
    assert.equal(p.data.canPreview, false);
});
test('目录空态和失败重试可恢复', async () => {
    let fail = true;
    const p = page('exam-papers', async () => { if (fail) throw Error('网络中断'); return { papers: [] }; });
    await p.load(); assert.equal(p.data.state, 'error'); assert.equal(p.data.errorMsg, '网络中断');
    fail = false; await p.load(); assert.equal(p.data.state, 'ready'); assert.deepEqual(p.data.papers, []);
});
test('学员只读取套卷概览，不请求草稿题目', async () => {
    const calls = [];
    const p = page('exam-paper', async url => { calls.push(url); return { id: 'p', question_count: 165, can_preview: false }; });
    p.onLoad({ id: 'p' }); await p.load();
    assert.equal(p.data.canPreview, false); assert.equal(p.data.question, null);
    assert.ok(calls.every(x => !x.includes('/questions/')));
});
test('教研逐题预览保留共用题干、选项、未解决状态与证据；按题号切换', async () => {
    const calls = [];
    const p = page('exam-paper', async url => {
        calls.push(url);
        if (!url.includes('/questions/')) return { id: 'p', title: '真题', can_preview: true, question_numbers: [1, 3] };
        return { number: Number(url.split('/').at(-1)), prompt: '题目', shared_stem: '病例', options: ['甲','乙'], answer: [], answer_status: 'unresolved', evidence: [{ quote: '原文' }], cards: [{ front: '提问', back: '候选内容' }] };
    });
    p.onLoad({ id: 'p' }); await p.load();
    assert.equal(p.data.question.shared_stem, '病例'); assert.equal(p.data.answerText, '答案未解决');
    assert.deepEqual(p.data.options, [{ letter:'A', text:'甲' }, { letter:'B', text:'乙' }]);
    await p.next(); assert.equal(p.data.question.number, 3); assert.equal(p.data.index, 1);
    assert.equal(p.data.question.evidence[0].quote, '原文');
    await p.next(); assert.equal(p.data.index, 1);
});
test('切题失败清除旧题并允许重试，候选答案始终标注待审核', async () => {
    let fail = false;
    const p = page('exam-paper', async url => {
        if (!url.includes('/questions/')) return { can_preview:true, question_numbers:[1,2] };
        if (fail) throw Error('读取失败');
        return { number: 1, options:[], answer:['A','C'], answer_status:'candidate' };
    });
    p.onLoad({id:'p'}); await p.load(); assert.equal(p.data.answerText, '候选答案：A、C · 待审核');
    fail = true; await p.next(); assert.equal(p.data.question, null); assert.equal(p.data.questionState, 'error');
    fail = false; await p.retryQuestion(); assert.equal(p.data.questionState, 'ready');
});
test('两页注册齐全，首页入口可达，新增模板不提供正式作答或积分按钮', () => {
    const config = JSON.parse(fs.readFileSync(path.join(miniRoot, 'app.json')));
    for (const name of ['exam-papers', 'exam-paper']) {
        assert.ok(config.pages.includes('pages/' + name + '/' + name));
        for (const ext of ['js','json','wxml','wxss']) assert.ok(fs.existsSync(path.join(miniRoot,'pages',name,name+'.'+ext)));
    }
    assert.match(fs.readFileSync(path.join(miniRoot,'pages/home/home.wxml'),'utf8'), /十年真题/);
    assert.match(fs.readFileSync(path.join(miniRoot,'pages/exam-paper/exam-paper.wxml'),'utf8'), /待审核/);
});
test('年度目录沿用当前网络通道与 Cookie，GET 不写入学习数据', async () => {
    const calls = [];
    const request = options => {
        calls.push(options);
        options.success(calls.length === 1
            ? { statusCode:200, data:{csrf:'fixture',user:{institution_id:'org'}}, header:{'Set-Cookie':'mdd_learner=fixture; Path=/'} }
            : { statusCode:200, data:{papers:[],can_preview:false} });
    };
    const wx = { request, cloud:{ init(){}, callContainer:request } };
    const module = {exports:{}};
    new Function('wx','module','exports',fs.readFileSync(path.join(miniRoot,'utils/api.js'),'utf8'))(wx,module,module.exports);
    const result = await module.exports.api('exam-papers');
    assert.deepEqual(result.papers, []);
    assert.equal(calls[1].method, 'GET');
    assert.equal(calls[1].header.Cookie, 'mdd_learner=fixture');
    if (calls[1].path) {
        assert.equal(calls[1].path, '/api/learn/exam-papers');
        assert.equal(calls[1].header['X-WX-SERVICE'], 'mdd-learner-api');
    } else {
        assert.equal(calls[1].url, 'https://mdd.gesturedraw.fun/api/learn/exam-papers');
        assert.equal(calls[1].header['X-Institution-ID'], 'org');
    }
});
test('较旧的题目响应不会覆盖最后选择的题目', async () => {
    const pending = [];
    const p = page('exam-paper', url => new Promise(resolve => pending.push({url,resolve})));
    p._id='p';p._numbers=[1,2];p.data.canPreview=true;
    const first=p.loadQuestion(0), second=p.loadQuestion(1);
    pending[1].resolve({number:2,options:[]});await second;
    pending[0].resolve({number:1,options:[]});await first;
    assert.equal(p.data.question.number,2);
});
test('年度目录重复刷新及离开页面后，不接受过期响应', async () => {
    const pending=[];
    const p=page('exam-papers',()=>new Promise(resolve=>pending.push(resolve)));
    const first=p.load(),second=p.load();
    pending[1]({papers:[{id:'new',year:2026,question_count:165}],can_preview:false});await second;
    pending[0]({papers:[{id:'old',year:2017,question_count:10}],can_preview:true});await first;
    assert.equal(p.data.papers[0].id,'new');assert.equal(p.data.canPreview,false);
    const last=p.load();p.onUnload();pending[2]({papers:[{id:'stale'}],can_preview:true});await last;
    assert.deepEqual(p.data.papers,[]);assert.equal(p.data.canPreview,false);
});
