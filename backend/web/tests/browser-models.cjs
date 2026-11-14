const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),path=require('path'),assert=require('assert');
(async()=>{
 const out=path.resolve(__dirname,'../../runtime');
 const b=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const p=await b.newPage({viewport:{width:1440,height:1050}}),errors=[],leaks=[];
 const fakeA='browser-dummy-key-a',fakeB='browser-dummy-key-b';
 p.on('pageerror',e=>errors.push(e.message));p.on('dialog',d=>d.accept());
 p.on('response',async r=>{if(r.url().includes('/api/')){try{const text=await r.text();if([fakeA,fakeB].some(k=>text.includes(k)))leaks.push(r.url())}catch{}}});
 const base='http://127.0.0.1:4313/';await p.goto(base+'#settings');await p.waitForSelector('#add-model');
 async function add(name,provider,model,key,url){await p.click('#add-model');await p.fill('#model-form [name=name]',name);await p.selectOption('#model-form [name=provider]',provider);await p.fill('#model-form [name=model]',model);if(url)await p.fill('#model-form [name=base_url]',url);assert.equal(await p.getAttribute('#model-form [name=api_key]','type'),'password');await p.fill('#model-form [name=api_key]',key);const response=p.waitForResponse(r=>r.url().endsWith('/api/models')&&r.request().method()==='POST');await p.click('#model-form [type=submit]');const r=await response;assert.equal(r.status(),200);await p.waitForSelector('#model-form',{state:'detached'});return r.json()}
 const a=await add('DeepSeek 出题','DeepSeek','deepseek-flash',fakeA);
 const c=await add('自定义推理','自定义兼容接口','custom-model-v2',fakeB,'https://custom.example/v1');
 await p.click(`[data-edit-model="${c.id}"]`);assert.equal(await p.inputValue('#model-form [name=api_key]'),'');await p.fill('#model-form [name=name]','自定义推理修订');const updated=p.waitForResponse(r=>r.url().endsWith('/api/models/'+c.id)&&r.request().method()==='POST');await p.click('#model-form [type=submit]');assert.equal((await updated).status(),200);await p.waitForSelector('#model-form',{state:'detached'});
 await p.click('#tab-limits');await p.fill('#settings-form [name=daily_call_limit]','2');await p.click('#settings-form [type=submit], #settings-form button');await p.waitForFunction(()=>document.querySelector('#toast').textContent.includes('调用上限已保存'));
 await p.click('nav a[href="#generate"]');await p.waitForSelector('#gen-model');await p.selectOption('#gen-model',a.id);assert((await p.locator('#chosen-model').innerText()).includes('DeepSeek'));await p.selectOption('#gen-model',c.id);assert((await p.locator('#chosen-model').innerText()).includes('https://custom.example/v1'));
 await p.selectOption('#gen-course','2112885753428808705');await p.fill('#generate-form [name=start]','138');await p.fill('#generate-form [name=end]','139');await p.fill('#generate-form [name=cards]','1');await p.fill('#generate-form [name=questions]','0');
 const enqueued=p.waitForResponse(r=>r.url().endsWith('/api/generate')&&r.request().method()==='POST');await p.click('#generate-form button');const response=await enqueued;assert.equal(response.status(),200,await response.text());await p.waitForSelector('#refresh-jobs');
 const jobs=await p.evaluate(()=>fetch('/api/jobs').then(r=>r.json()));assert.equal(jobs[0].config.model_profile.id,c.id);assert.equal(jobs[0].config.model_profile.model,'custom-model-v2');assert.equal(jobs[0].state,'queued');assert(!JSON.stringify(jobs).includes(fakeB));
 await p.click('nav a[href="#settings"]');await p.click('#tab-models');await p.waitForSelector(`[data-toggle-model="${c.id}"]`);await p.click(`[data-toggle-model="${c.id}"]`);await p.waitForFunction(id=>document.querySelector(`[data-toggle-model="${id}"]`).textContent==='启用',c.id);
 await p.click('nav a[href="#generate"]');await p.waitForSelector('#gen-model');assert(await p.locator(`#gen-model option[value="${c.id}"]`).isDisabled());assert.equal(await p.inputValue('#gen-model'),a.id);
 const layouts=[];for(const width of [1440,768,390,320]){await p.setViewportSize({width,height:1000});for(const page of ['settings','generate']){await p.goto(base+'#'+(page==='settings'?'settings/models':page));await p.waitForSelector(page==='settings'?'#add-model':'#gen-model');if(page==='settings')await p.click('#add-model');const size=await p.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));assert(size.document<=width,JSON.stringify(size));layouts.push({page,...size});if(page==='settings')await p.click('#cancel-model')}}
 await p.setViewportSize({width:1440,height:1000});await p.goto(base+'#settings/models');await p.waitForSelector('#add-model');await p.screenshot({path:out+'/models-test-preview.png',fullPage:true});assert.deepEqual(errors,[]);assert.deepEqual(leaks,[]);
 fs.writeFileSync(out+'/validation-models-browser.json',JSON.stringify({database:'knowledge_agent_test',flows:['add_two_models','masked_input','blank_key_retained','generation_selection','queued_snapshot','disable_selection','no_key_in_responses'],layouts,errors,leaks},null,2));
 await b.close();console.log(JSON.stringify({flows:7,layouts:layouts.length,errors,leaks}));
})().catch(e=>{console.error(e);process.exit(1)});
