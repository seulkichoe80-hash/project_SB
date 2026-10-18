"""Bounded opt-in C lexical scorer, no migration, vector model or generation."""
import heapq
import json
from .errors import DomainError
from .search_settings import normalize_search


class ScoredORSearch:
    method='sqlite_scored_or_v1'
    def __init__(self,settings):self.settings=settings
    def search(self,db,organization,terms,limit):
        if not terms:return []
        rows=db.connection.execute('''SELECT i.payload,i.search_text FROM chunk_items i
          JOIN chunk_current c ON c.job_id=i.job_id JOIN chunk_jobs j ON j.id=c.job_id
          JOIN versions v ON v.id=c.version_id JOIN documents d ON d.id=v.document_id
          JOIN parse_jobs p ON p.id=j.parse_job_id AND p.attempt=j.parse_attempt AND p.version_id=v.id
          WHERE d.institution_id=? AND d.registered=1 AND d.active_version_id=v.id
          AND j.state='completed' AND p.state='completed'
          ORDER BY d.created_at,v.id,i.order_index''',(organization,))
        top=[];scanned_bytes=0
        for ordinal,row in enumerate(rows,1):
            if ordinal>self.settings.max_scanned_chunks:raise DomainError('scored_or_corpus_limit',413)
            normalized=normalize_search(row['search_text'])
            scanned_bytes+=len(row['search_text'].encode())+len(normalized.encode())
            if scanned_bytes>self.settings.max_scanned_bytes:raise DomainError('scored_or_corpus_limit',413)
            score=sum(t in normalized for t in terms)
            if not score:continue
            entry=(score,-ordinal,row['payload'])
            if len(top)<limit:heapq.heappush(top,entry)
            elif entry[:2]>top[0][:2]:heapq.heapreplace(top,entry)
        return [json.loads(payload) for _,_,payload in sorted(top,key=lambda x:(-x[0],-x[1]))]
