import unittest,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from processing import parse_material,chunks,validate_content
from docx import Document
class ParserTests(unittest.TestCase):
 def test_word_paragraph_and_table_order(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'sample.docx';doc=Document();doc.add_heading('第一章',1);doc.add_paragraph('第一段原文');t=doc.add_table(rows=1,cols=2);t.cell(0,0).text='左';t.cell(0,1).text='右';doc.add_paragraph('表后段落');doc.save(p)
   result=parse_material({'path':str(p),'type':'docx'})
   self.assertEqual([x['text'] for x in result['chunks']],['第一章','第一段原文','左\t右','表后段落'])
   self.assertTrue(all('第一章' in x['label'] for x in result['chunks']))
 def test_unsupported_parse_fails_explicitly(self):
  with self.assertRaises(ValueError):parse_material({'path':'/tmp/no-file','type':'mp4'})
 def test_choice_answer_mismatch_is_not_corrected_silently(self):
  with self.assertRaises(ValueError):validate_content({'prompt':'问题','answer':'A. 不同原文','ai_explanation':'解释','difficulty':'基础','tags':['测试'],'options':['甲','乙','丙','丁'],'answer_indices':[0]},'single_choice')
