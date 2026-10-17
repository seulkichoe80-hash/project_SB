import copy,importlib.util,json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts/validation'/f'{name}.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
workflow=load('workflow_contract');retrieval=load('evaluate_retrieval')
hwpx=load('probe_hwpx')

class ContractTests(unittest.TestCase):
    def test_invalid_pixel_original_rejected_and_corrected_fixture_valid(self):
        # Historical v1 was missing on 2026-10-17. Use the explicitly new CRC-negative
        # fixture; preserve the v1 manifest and never claim byte-identical restoration.
        with self.assertRaises(ValueError):hwpx.extract(ROOT/'tests/fixtures/synthetic/procedure-recovery-invalid.hwpx')
        self.assertEqual(hwpx.extract(ROOT/'tests/fixtures/synthetic/procedure-v2.hwpx')['anchor_roundtrip_count'],9)
    def setUp(self):
        self.e={'tenant_id':'A','document_id':'d1','version_id':'v1','element_id':'p1','quote':'신청서를 작성한다.'}
        assertion={'text':'신청서를 작성한다.','evidence':[self.e]}
        self.payload={'workflow_id':'w1','title':assertion,'steps':[{'id':'s1','label':assertion,'actions':[assertion],'deadline':None,'required_documents':[]}],'edges':[],'unresolved_issues':[]}
        self.registry={('d1','v1','p1'):{'tenant_id':'A','source_kind':'original_text','text':'1. 신청서를 작성한다.','location':{'part':'Contents/section0.xml','path':'/sec/p[1]'}}}
    def verify(self,payload):return workflow.verify(payload,self.registry,'A',{('d1','v1')})
    def test_valid_stays_candidate(self):
        result=self.verify(self.payload);self.assertEqual(result['status'],'candidate');self.assertEqual(result['semantic_validation'],'NOT_RUN')
    def test_missing_quote_and_location_rejected(self):
        for key in ['text','location']:
            r=copy.deepcopy(self.registry);r[('d1','v1','p1')][key]='' if key=='text' else None
            with self.assertRaises(ValueError):workflow.verify(self.payload,r,'A',{('d1','v1')})
    def test_foreign_inactive_or_unknown_rejected(self):
        for mut in ['foreign','unknown','inactive']:
            p=copy.deepcopy(self.payload)
            if mut=='foreign':p['title']['evidence'][0]['tenant_id']='B'
            elif mut=='unknown':p['title']['evidence'][0]['element_id']='missing'
            with self.assertRaises(ValueError):workflow.verify(p,self.registry,'A',set() if mut=='inactive' else {('d1','v1')})
    def test_ungrounded_and_extra_fields_rejected(self):
        for mut in ['missing','extra','duplicate','edge','deadline']:
            p=copy.deepcopy(self.payload)
            if mut=='missing':p['title']['evidence']=[]
            elif mut=='extra':p['steps'][0]['untrusted_command']='run'
            elif mut=='duplicate':p['steps'].append(copy.deepcopy(p['steps'][0]))
            elif mut=='edge':p['edges']=[{'id':'e','source':'s1','target':'unknown','relation':'precedes','explanation':p['title']}]
            elif mut=='deadline':p['steps'][0]['deadline']={'text':'3일 이내 제출','evidence':[self.e]}
            with self.assertRaises(ValueError):self.verify(p)
    def test_existing_but_irrelevant_quote_not_marked_verified(self):
        p=copy.deepcopy(self.payload);p['title']['text']='승인 없이 비용을 지급한다.'
        # Referential validation cannot prove meaning: result must remain unverified candidate.
        self.assertTrue(all(c['semantic_review_required'] for c in self.verify(p)['claims']))
    def test_ai_description_cannot_replace_original(self):
        r=copy.deepcopy(self.registry);r[('d1','v1','p1')]['source_kind']='ai_description'
        with self.assertRaises(ValueError):workflow.verify(self.payload,r,'A',{('d1','v1')})
    def test_metrics_and_scope_leak(self):
        q=[{'id':'q1','expected':['a'],'allowed_tenants':['A']},{'id':'q2','expected':[],'allowed_tenants':['A']}]
        registry={'a':{'tenant_id':'A','active':True},'b':{'tenant_id':'B','active':True}}
        valid=retrieval.score(q,{'q1':['a'],'q2':[]},registry,mode='metric_fixture');self.assertEqual(valid['hit_at_5'],1);self.assertFalse(valid['actual_embedding_executed'])
        invalid=retrieval.score(q,{'q1':['b','a'],'q2':[]},registry,mode='metric_fixture');self.assertFalse(invalid['safety_pass'])
    def test_actual_embedding_metadata_and_duplicates_required(self):
        q=[{'id':'q','expected':['a'],'allowed_tenants':['A']}];r={'a':{'tenant_id':'A','active':True}}
        with self.assertRaises(ValueError):retrieval.score(q,{'q':['a']},r,mode='actual_embedding')
        with self.assertRaises(ValueError):retrieval.score(q,{'q':['a','a']},r,mode='metric_fixture')

if __name__=='__main__':unittest.main()
