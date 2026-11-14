import unittest, importlib.util, tempfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('parser',Path(__file__).resolve().parents[1]/'parse_samples.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class ParseTests(unittest.TestCase):
 def test_time_validation(self):
  self.assertEqual(m.time_ms('02:01:00,610'),7260610)
  for t in ['00:61:00,000','bad','00:00:00']:
   with self.assertRaises(ValueError):m.time_ms(t)
 def test_csv_preserves_long_id_quotes_and_multiline(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.csv';p.write_text('courseware_id,num,start,end,text\n2112195317365912484,1,"00:00:01,000","00:00:02,000","首句,带逗号\n第二行"\n',encoding='utf-8')
   result=m.parse_csv(p);row=result['groups']['2112195317365912484'][0]
   self.assertEqual(row['text'],'首句,带逗号\n第二行');self.assertEqual(row['row_index'],2)
 def test_real_csv_integrity(self):
  d=m.parse_csv(m.CSV_PATH);self.assertEqual(d['record_count'],6680);self.assertEqual(len(d['groups']),6);self.assertEqual(d['issues'],[])
  self.assertTrue(all(s['sequence_contiguous'] and not s['overlap_rows'] and not s['backwards_rows'] for s in d['summary']))
 def test_real_pdf_page_and_question_provenance(self):
  for year,count,last in [('2016',31,180),('2017',29,165),('2018',30,165)]:
   d=m.parse_pdf(next(m.PDF_ROOT.glob('【'+year+'】*.pdf')),year)
   self.assertEqual(d['page_count'],count);self.assertEqual([q['number'] for q in d['question_starts']],list(range(1,last+1)))
   self.assertEqual(d['answer_markers'],[]);self.assertTrue(all(p['page']==p['printed_page'] for p in d['pages']))
   for q in d['question_starts']:self.assertIn(q['first_line'],d['pages'][q['page']-1]['text'])
   if year=='2018':self.assertTrue(next(q for q in d['question_starts'] if q['number']==15)['first_line'].startswith('1,25'))
if __name__=='__main__':unittest.main()
