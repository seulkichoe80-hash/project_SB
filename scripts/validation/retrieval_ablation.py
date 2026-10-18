"""Preregistered offline A/B/C/D ablations. No provider, product index change or response generation."""
import copy
import math
import sqlite3
import time
import unicodedata
from apps.api.chunking import canonical,digest
from apps.api.errors import DomainError
from scripts.validation.evaluation_fixtures import EvaluationQueryAdapter
from scripts.validation.fixed_context_evaluation import FixedContextBuilder

METHODS=('A','B','C','D')
NORMALIZATION_VERSION='nfkc-punctuation-whitespace-v1'


def normalize(text):
    value=unicodedata.normalize('NFKC',text).casefold()
    return ' '.join(''.join(' ' if unicodedata.category(c).startswith('P') else c for c in value).split())


def query_tokens(question,method):
    if method not in METHODS:raise ValueError('unknown_ablation_method')
    # Apply the existing envelope before normalization; never silently truncate.
    EvaluationQueryAdapter.windows(question)
    text=question if method=='A' else normalize(question)
    if not text:return text,[]
    tokens=text.casefold().split()
    if len(text)>4000 or len(tokens)>128 or any(len(t)>200 for t in tokens):raise ValueError('ablation_query_limit')
    return text,list(dict.fromkeys(tokens))


def literal_pattern(term):return '%'+term.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'


def key(item):
    ref=item['evidence'];return (ref['document_id'],ref['version_id'],ref['chunk_id'])


class AblationSearch:
    """Tenant-scoped in-memory projections of verified current source rows; explicit lifecycle."""
    def __init__(self,chunks,generation):
        self.chunks=chunks;self.generation=copy.deepcopy(generation);self.builder=FixedContextBuilder(chunks,generation)
        self.connections={};self.packets={};self.items={};self.resolved=set();self.fts_supported=True
        started=time.perf_counter()
        try:
            for org in sorted({d['organization_id'] for d in generation['documents']}):
                packet=self.builder.build(org);self.packets[org]=packet
                c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row;self.connections[org]=c
                c.execute('CREATE TABLE items(ordinal INTEGER PRIMARY KEY,chunk_id TEXT UNIQUE,raw_text TEXT,normalized_text TEXT)')
                try:c.execute("CREATE VIRTUAL TABLE ft USING fts5(text, tokenize='unicode61 remove_diacritics 0')")
                except sqlite3.OperationalError:self.fts_supported=False
                canonical_items={key(x):x for x in packet['chunks']}
                with chunks.repo.transaction() as db:
                    rows=db.connection.execute('''SELECT i.payload,i.search_text,j.id AS chunk_job_id,j.generation,v.document_id,v.id AS version_id
                      FROM chunk_items i JOIN chunk_current cc ON cc.job_id=i.job_id JOIN chunk_jobs j ON j.id=i.job_id
                      JOIN versions v ON v.id=cc.version_id JOIN documents d ON d.id=v.document_id
                      JOIN parse_jobs p ON p.id=j.parse_job_id AND p.attempt=j.parse_attempt
                      WHERE d.institution_id=? AND d.registered=1 AND d.active_version_id=v.id
                      AND j.state='completed' AND p.state='completed'
                      ORDER BY d.created_at,v.id,i.order_index''',(org,)).fetchall()
                if len(rows)!=len(canonical_items):raise DomainError('ablation_index_scope_changed',409)
                self.items[org]={};seen=set()
                import json
                for ordinal,row in enumerate(rows,1):
                    item=json.loads(row['payload']);k=key(item)
                    if k in seen or canonical_items.get(k)!=item:raise DomainError('ablation_forged_index',422)
                    seen.add(k);self.builder.resolver(org,item['evidence']);self.resolved.add((org,canonical(item['evidence'])))
                    self.items[org][item['chunk_id']]=item
                    normalized=normalize(row['search_text'])
                    c.execute('INSERT INTO items VALUES (?,?,?,?)',(ordinal,item['chunk_id'],row['search_text'],normalized))
                    if self.fts_supported:c.execute('INSERT INTO ft(rowid,text) VALUES (?,?)',(ordinal,normalized))
                c.commit();self.builder.validate(org,packet)
            self.index_build_seconds=time.perf_counter()-started
        except Exception:self.close();raise
    def close(self):
        for c in self.connections.values():c.close()
        self.connections={}
    def reset_verification_cache(self):self.resolved.clear()
    def _rank(self,org,question,method):
        text,tokens=query_tokens(question,method);c=self.connections[org]
        if method=='D' and not self.fts_supported:raise DomainError('fts5_unavailable',503)
        if not tokens:return [],text,tokens
        if method in ('A','B'):
            scores={};column='raw_text' if method=='A' else 'normalized_text'
            # Preserve all words in each window, including repeated tokens, as in the old adapter.
            for window in EvaluationQueryAdapter.windows(text):
                terms=window.casefold().split();where=' AND '.join(f"{column} LIKE ? ESCAPE '\\'" for _ in terms)
                rows=c.execute('SELECT chunk_id FROM items WHERE '+where+' ORDER BY ordinal LIMIT 50',tuple(literal_pattern(t) for t in terms)).fetchall()
                for rank,row in enumerate(rows,1):scores[row['chunk_id']]=scores.get(row['chunk_id'],0)+1/(60+rank)
            ids=sorted(scores,key=lambda x:(-scores[x],key(self.items[org][x])))
            return [{'chunk_id':x,'score':scores[x],'score_kind':'rrf60_higher_is_better'} for x in ids],text,tokens
        if method=='C':
            expression='+'.join('(instr(normalized_text,?)>0)' for _ in tokens)
            rows=c.execute('SELECT chunk_id,'+expression+' AS score FROM items WHERE score>0 ORDER BY score DESC,ordinal',tuple(tokens)).fetchall()
            return [{'chunk_id':r['chunk_id'],'score':r['score'],'score_kind':'matched_distinct_tokens_higher_is_better'} for r in rows],text,tokens
        # Quote each term inside FTS MATCH in addition to SQL parameter binding. No operators from input.
        match=' OR '.join('"'+t.replace('"','""')+'"' for t in tokens)
        rows=c.execute('SELECT i.chunk_id,bm25(ft) AS score FROM ft JOIN items i ON i.ordinal=ft.rowid WHERE ft MATCH ? ORDER BY score,i.ordinal',(match,)).fetchall()
        return [{'chunk_id':r['chunk_id'],'score':r['score'],'score_kind':'sqlite_bm25_lower_is_better'} for r in rows],text,tokens
    def search(self,principal,question,method,limit=57):
        if principal is None or principal.role not in ('reader','manager'):raise DomainError('ablation_access_denied',403)
        if type(limit) is not int or not 1<=limit<=57:raise ValueError('ablation_result_limit')
        org=principal.institution_id
        if org not in self.packets:raise DomainError('ablation_scope_not_found',404)
        total=time.perf_counter();self.builder.validate(org,self.packets[org])
        started=time.perf_counter();ranked,text,tokens=self._rank(org,question,method);rank_seconds=time.perf_counter()-started
        ranked=ranked[:limit];results=[]
        allowed={x['chunk_id']:x for x in self.packets[org]['chunks']}
        for r in ranked:
            item=self.items[org].get(r['chunk_id'])
            if item is None or item!=allowed.get(r['chunk_id']):raise DomainError('ablation_result_outside_context',422)
            proof=(org,canonical(item['evidence']))
            if proof not in self.resolved:self.builder.resolver(org,item['evidence']);self.resolved.add(proof)
            results.append({'chunk':copy.deepcopy(item),'score':r['score'],'score_kind':r['score_kind']})
        # A cached citation proof is usable only inside the same freshly revalidated immutable snapshot.
        self.builder.validate(org,self.packets[org])
        return {'method':method,'question':question,'normalized_question':text,'tokens':tokens,'results':results,
            'ranking_seconds':rank_seconds,'end_to_end_seconds':time.perf_counter()-total,
            'response_status':'CANDIDATE_CONTEXT_ONLY_NO_ANSWER' if results else 'INSUFFICIENT_RETRIEVAL_NO_ANSWER',
            'answer_generated':False,'semantic_verification':'NOT_VERIFIED','goldset_status':'PROVISIONAL','actual_provider_calls':0}


def query_metrics(expected,ranked):
    expected=set(expected)
    if not expected:raise ValueError('positive_denominator_required')
    if len(ranked)!=len(set(ranked)):raise ValueError('duplicate_ranked_evidence')
    rr=next((1/(i+1) for i,k in enumerate(ranked) if k in expected),0)
    output={'mrr':rr,'mrr_at_10':rr if any(k in expected for k in ranked[:10]) else 0,'no_results':not ranked}
    for k in (5,10):
        found=expected&set(ranked[:k]);output[f'hit_at_{k}']=int(bool(found));output[f'recall_at_{k}']=len(found)/len(expected)
    return output


def latency(values):
    if not values:return {'samples':0,'mean_ms':None,'p50_ms':None,'p95_ms':None,'total_seconds':0}
    v=sorted(values);return {'samples':len(v),'mean_ms':sum(v)*1000/len(v),'p50_ms':v[(len(v)-1)//2]*1000,
        'p95_ms':v[math.ceil(.95*len(v))-1]*1000,'total_seconds':sum(v)}
