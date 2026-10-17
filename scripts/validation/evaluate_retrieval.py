"""Offline rank scorer. It never creates embeddings or queries a model."""
def score(queries,rankings,registry,*,mode,model_metadata=None):
    if mode not in {'metric_fixture','actual_embedding'}:raise ValueError('explicit mode required')
    if mode=='actual_embedding' and not all((model_metadata or {}).get(k) for k in ['provider','model','dimension','index_generation']):raise ValueError('actual model metadata required')
    hits=0;recalls=[];rr=[];no_answer_fp=0;violations=[];answerable=0;no_answer=0
    for q in queries:
        ranked=rankings.get(q['id'],[])[:5]
        if len(ranked)!=len(set(ranked)):raise ValueError('duplicate ranking id')
        for element_id in ranked:
            doc=registry.get(element_id)
            if not doc:raise ValueError('unknown result id')
            if doc['tenant_id'] not in q['allowed_tenants'] or not doc['active']:violations.append({'query':q['id'],'element':element_id})
        expected=set(q['expected'])
        if expected:
            answerable+=1;found=expected.intersection(ranked);hits+=bool(found);recalls.append(len(found)/len(expected));rr.append(next((1/(i+1) for i,e in enumerate(ranked) if e in expected),0))
        else:no_answer+=1;no_answer_fp+=bool(ranked)
    if answerable==0:raise ValueError('no answerable denominator')
    return {'mode':mode,'answerable':answerable,'hit_at_5':hits/answerable,'recall_at_5':sum(recalls)/answerable,'mrr_at_5':sum(rr)/answerable,'no_answer_queries':no_answer,'no_answer_false_positives':no_answer_fp,'scope_violations':violations,'safety_pass':not violations,'actual_embedding_executed':mode=='actual_embedding'}
