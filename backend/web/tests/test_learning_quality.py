import copy,json,unittest
from unittest.mock import patch
import test_app
from db import one
from learning_quality import validate_design,pending_exam_context
import processing

SOURCE=[{'source_id':'s1','text':'甲过程使指标升高，乙过程使指标降低。两者的作用方向不同。'}]
def design():
 return {'outline_node_id':None,'exam_question_ids':[],'objective':'辨析作用方向','misconception':{'basis':'none','summary':'','evidence':[]},'option_explanations':[]}
def exam_context():
 return {'syllabus_nodes':[{'id':'node-a','title':'测试大纲节点','path':'第一章 / 作用方向'}],
 'verified_questions':[{'id':'q17','verified':True,'outline_node_id':'node-a','year':2017,'paper_id':'paper-2017','question_number':2,'source_id':'p1','material_id':'2017'},
 {'id':'q17-duplicate','verified':True,'outline_node_id':'node-a','year':2017,'paper_id':'paper-2017','question_number':2,'source_id':'p2','material_id':'copy'},
 {'id':'q18','verified':True,'outline_node_id':'node-a','year':2018,'paper_id':'paper-2018','question_number':5,'source_id':'p3','material_id':'2018'}],
 'fully_reviewed_years':[2017,2018]}

class LearningQualityTests(unittest.TestCase):
 def test_missing_data_is_unknown_not_zero(self):
  q=validate_design(design(),'card',[],SOURCE,pending_exam_context())
  self.assertIsNone(q['outline']);self.assertIsNone(q['coverage']['question_count']);self.assertEqual(q['coverage']['period'],[2017,2026]);self.assertEqual(q['coverage']['status'],'not_verified')
 def test_fabricated_outline_or_exam_reference_blocked(self):
  d=design();d['outline_node_id']='invented'
  with self.assertRaises(ValueError):validate_design(d,'card',[],SOURCE,pending_exam_context())
  d=design();d['exam_question_ids']=['guessed-2025']
  with self.assertRaises(ValueError):validate_design(d,'card',[],SOURCE,pending_exam_context())
 def test_dedup_count_all_verified_matches_not_model_subset(self):
  d=design();d['outline_node_id']='node-a';d['exam_question_ids']=['q17']
  q=validate_design(d,'card',[],SOURCE,exam_context())
  self.assertEqual(q['coverage']['question_count'],2);self.assertEqual(q['coverage']['years'],[2017,2018]);self.assertEqual(q['coverage']['status'],'partial')
 def test_2016_excluded_and_claimed_2016_rejected(self):
  ctx=exam_context();ctx['verified_questions'][0]['year']=2016;d=design();d['outline_node_id']='node-a';d['exam_question_ids']=['q17']
  with self.assertRaises(ValueError):validate_design(d,'card',[],SOURCE,ctx)
 def test_zero_only_labeled_with_reviewed_scope(self):
  ctx=exam_context();ctx['verified_questions']=[];ctx['fully_reviewed_years']=list(range(2017,2027));d=design();d['outline_node_id']='node-a'
  q=validate_design(d,'card',[],SOURCE,ctx);self.assertEqual(q['coverage']['status'],'complete');self.assertEqual(q['coverage']['question_count'],0)
  ctx['fully_reviewed_years']=[];self.assertIsNone(validate_design(d,'card',[],SOURCE,ctx)['coverage']['question_count'])
 def test_counters_cannot_be_supplied_by_model(self):
  d=design();d['coverage_count']=10
  with self.assertRaises(ValueError):validate_design(d,'card',[],SOURCE,pending_exam_context())
 def test_misconception_requires_literal_evidence(self):
  d=design();d['misconception']={'basis':'design_hypothesis','summary':'潜在混淆：因果方向颠倒','evidence':[{'source_id':'s1','quote':'完全不存在的原文'}]}
  with self.assertRaises(ValueError):validate_design(d,'card',[],SOURCE,pending_exam_context())
  d['misconception']['evidence'][0]['quote']='甲过程使指标升高';q=validate_design(d,'card',[],SOURCE,pending_exam_context());self.assertEqual(q['misconception']['basis'],'design_hypothesis')
 def test_question_requires_every_option_explained_and_evidenced(self):
  d=design();opts=['甲','乙','丙','丁'];d['option_explanations']=[{'index':i,'explanation':'对照原文说明该选项的作用方向','evidence':[{'source_id':'s1','quote':'甲过程使指标升高'}]} for i in range(4)]
  self.assertEqual(len(validate_design(d,'single_choice',opts,SOURCE,pending_exam_context())['option_explanations']),4)
  d['option_explanations'].pop()
  with self.assertRaises(ValueError):validate_design(d,'single_choice',opts,SOURCE,pending_exam_context())

class GenerationQualityIntegration(unittest.TestCase):
 setUp=test_app.AppTests.setUp
 def test_generated_quality_is_persisted_pending(self):
  item=one("SELECT * FROM items WHERE id='C01'");material=one("SELECT * FROM materials WHERE id='transcript'")
  output={**item['current'],'kind':'card','evidence':item['evidence']['evidence'],'learning_design':design()}
  cfg={'course':'2112885753428808705','start':138,'end':139,'cards':1,'questions':0,'question_type':'single_choice','prompt':{'content':'test'},'settings':{'model':'test'},'quality_policy_version':1,'exam_context':pending_exam_context()}
  def mocked(job,purpose,messages):
   if purpose=='generation':
    payload=json.loads(messages[-1]['content']);self.assertEqual(payload['exam_context']['period'],[2017,2026]);return {'items':[output]}
   prepared=json.loads(messages[-1]['content']);return {'checks':[{'id':p['id'],'supported':True,'reason':'隔离测试返回'} for p in prepared]}
  with patch('processing.model_call',side_effect=mocked):processing.generate({'id':'quality-test','config':cfg},material)
  saved=one("SELECT * FROM items WHERE batch_id='quality-test'")
  self.assertEqual(saved['status'],'pending_review');self.assertIsNone(saved['evidence']['learning_quality']['coverage']['question_count'])
