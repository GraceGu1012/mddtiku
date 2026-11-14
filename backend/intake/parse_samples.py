"""Read-only local intake validation; no model, ASR or database calls."""
from pathlib import Path
from collections import defaultdict, Counter
import csv, io, re, hashlib, json, shutil
import fitz

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'designs/knowledge-agent-intake'
PDF_ROOT=Path('/Users/grace/Library/Application Support/MDDClass/Users/175120370/ShareFiles')
CSV_PATH=Path('/Users/grace/Desktop/天天师兄字幕.csv')

def time_ms(value):
    m=re.fullmatch(r'(\d+):([0-5]\d):([0-5]\d)[,.](\d{3})', value)
    if not m: raise ValueError('invalid timestamp')
    h,minute,second,ms=map(int,m.groups())
    return ((h*60+minute)*60+second)*1000+ms

def parse_csv(path):
    raw=path.read_bytes()
    encoding=next((e for e in ['utf-8-sig','gb18030'] if decodable(raw,e)),None)
    if not encoding: raise ValueError('Unsupported CSV encoding')
    reader=csv.DictReader(io.StringIO(raw.decode(encoding),newline=''))
    if reader.fieldnames!=['courseware_id','num','start','end','text']: raise ValueError('Unexpected CSV header')
    groups=defaultdict(list);issues=[]
    for index,row in enumerate(reader,2):
        # row_index is logical record index (including header), not physical text line.
        record={**row,'row_index':index,'source_id':f'csv-record-{index}'}
        try:
            record['start_ms']=time_ms(row['start']);record['end_ms']=time_ms(row['end'])
            if record['end_ms']<=record['start_ms']: issues.append({'row':index,'kind':'nonpositive_duration'})
        except (ValueError,TypeError):
            record['start_ms']=record['end_ms']=None;issues.append({'row':index,'kind':'invalid_timestamp'})
        if not row.get('text','').strip():issues.append({'row':index,'kind':'empty_text'})
        groups[row['courseware_id']].append(record)
    summaries=[]
    for course,rows in groups.items():
        nums=[r['num'] for r in rows];duplicates=[n for n,c in Counter(nums).items() if c>1]
        overlaps=[];backwards=[];gaps=[]
        for prev,cur in zip(rows,rows[1:]):
            if prev['start_ms'] is None or cur['start_ms'] is None:continue
            if cur['start_ms']<prev['start_ms']:backwards.append(cur['row_index'])
            if cur['start_ms']<prev['end_ms']:overlaps.append(cur['row_index'])
            if cur['start_ms']-prev['end_ms']>30000:gaps.append(cur['row_index'])
        summaries.append({'courseware_id':course,'rows':len(rows),'first':rows[0]['start'],'last':rows[-1]['end'],'span_ms':max(r['end_ms'] for r in rows if r['end_ms'] is not None)-min(r['start_ms'] for r in rows if r['start_ms'] is not None),'duplicate_nums':duplicates,'sequence_contiguous':nums==[str(i) for i in range(1,len(rows)+1)],'overlap_rows':overlaps,'backwards_rows':backwards,'gaps_over_30s':gaps})
    return {'encoding':encoding,'headers':reader.fieldnames,'record_count':sum(map(len,groups.values())),'groups':dict(groups),'summary':summaries,'issues':issues}

def decodable(raw,enc):
    try:raw.decode(enc);return True
    except UnicodeDecodeError:return False

def parse_pdf(path,year):
    d=fitz.open(path);pages=[];headings=[];questions=[];answer_markers=[];ignored_numeric_lines=[]
    for i,page in enumerate(d):
        text=page.get_text('text',sort=True)
        number=re.search(r'(?m)^\s*-\s*(\d+)\s*-\s*$',text)
        lines=[]
        for block in page.get_text('dict',sort=True)['blocks']:
            for line in block.get('lines',[]):
                val=''.join(s['text'] for s in line['spans'])
                lines.append({'text':val,'bbox':[round(n,2) for n in line['bbox']]})
        hits=re.findall(r'(?m)^\s*(\d{1,3})[.．、]\s*(.+)',text)
        for num,stem in hits:
            item={'number':int(num),'page':i+1,'first_line':stem.strip()}
            if questions and int(num)<=questions[-1]['number']:ignored_numeric_lines.append(item)
            else:questions.append(item)
        for l in text.splitlines():
            if re.match(r'^[一二三]、[ABX]\s*型题',l.strip()):headings.append({'page':i+1,'title':l.strip()})
            if re.search(r'参考答案|答案解析|正确答案|答案\s*[:：]',l):answer_markers.append({'page':i+1,'text':l})
        pages.append({'source_id':f'pdf-{year}-page-{i+1}','page':i+1,'printed_page':int(number.group(1)) if number else None,'width':page.rect.width,'height':page.rect.height,'text':text,'lines':lines,'image_count':len(page.get_images())})
    return {'page_count':len(d),'bookmarks':d.get_toc(),'pages':pages,'headings':headings,'question_starts':questions,'answer_markers':answer_markers,'ignored_numeric_lines':ignored_numeric_lines,'empty_pages':[p['page'] for p in pages if not p['text'].strip()],'replacement_chars':sum(p['text'].count('\ufffd') for p in pages)}

def write_json(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def identity(path):return {'filename':path.name,'size':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def main():
    for name in ['data','sources','previews']:(OUT/name).mkdir(parents=True,exist_ok=True)
    manifest={'run_date':'2026-11-09','stage':'local_parse_only','model_calls':0,'asr_calls':0,'database_used':False,'materials':[]}
    parsed=parse_csv(CSV_PATH);write_json(OUT/'data/transcript.json',parsed);shutil.copyfile(CSV_PATH,OUT/'sources/transcript.csv')
    manifest['materials'].append({'id':'transcript',**identity(CSV_PATH),'type':'csv','record_count':parsed['record_count'],'course_count':len(parsed['groups']),'issues':parsed['issues'],'summary':parsed['summary']})
    for year in ['2016','2017','2018']:
        path=next(PDF_ROOT.glob('【'+year+'】*.pdf'));result=parse_pdf(path,year);write_json(OUT/f'data/pdf-{year}.json',result);shutil.copyfile(path,OUT/f'sources/{year}.pdf')
        samples=sorted(set([1,result['page_count']]+([3] if year=='2018' else [])+[h['page'] for h in result['headings']][1:]))
        with fitz.open(path) as d:
            for page in samples:d[page-1].get_pixmap(matrix=fitz.Matrix(1.3,1.3)).save(OUT/f'previews/{year}-{page}.png')
        nums=[q['number'] for q in result['question_starts']];maximum=max(nums)
        manifest['materials'].append({'id':year,**identity(path),'type':'pdf','pages':result['page_count'],'chars':sum(len(p['text']) for p in result['pages']),'empty_pages':result['empty_pages'],'replacement_chars':result['replacement_chars'],'headings':result['headings'],'question_start_count':len(nums),'missing_question_numbers':sorted(set(range(1,maximum+1))-set(nums)),'duplicate_question_numbers':[n for n,c in Counter(nums).items() if c>1],'answer_markers':result['answer_markers'],'ignored_numeric_lines':result['ignored_numeric_lines'],'printed_page_mismatches':[p['page'] for p in result['pages'] if p['printed_page']!=p['page']],'sample_pages':samples})
    write_json(OUT/'data/manifest.json',manifest)
    print(json.dumps(manifest,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
