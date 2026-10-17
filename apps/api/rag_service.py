"""Opt-in local RAG contracts; no network transport or implicit model fallback."""
from .chunking import Chunk, EvidenceRef
from .errors import DomainError
from .rag_adapters import Generation, checked_vectors
from .vector_repository import SQLiteVectorStore


class RAGService:
    def __init__(self, chunks, embedding, llm=None, vector_store=None):
        # Only explicitly injected offline doubles are enabled in this phase.
        if not embedding.spec.test_only or (llm is not None and not llm.test_only):
            raise DomainError('real_provider_not_enabled',503)
        self.chunks,self.embedding,self.llm=chunks,embedding,llm
        self.store=vector_store or SQLiteVectorStore(chunks.repo)

    def principal(self, principal, manager=False):
        if principal is None:
            raise DomainError('authentication_required',401)
        self.chunks.documents.role(principal,*(['manager'] if manager else ['reader','manager']))

    def validate(self, principal, item):
        chunk=Chunk.model_validate(item)
        ref=chunk.evidence
        if ref.organization_id != principal.institution_id:
            raise DomainError('foreign_evidence',404)
        with self.chunks.repo.transaction() as db:
            doc,_=self.chunks.documents.version(db,principal,ref.document_id,ref.version_id)
            if doc['active_version_id'] != ref.version_id:
                raise DomainError('inactive_search_evidence')
        resolved=self.chunks.resolve(principal,ref.document_id,ref.version_id,ref.chunk_id,ref)
        # Recheck whole payload, not only citations: hostile search adapters cannot invent text.
        canonical=self.chunks.list(principal,ref.document_id,ref.version_id)
        if item not in canonical or not resolved['structural_valid']:
            raise DomainError('invalid_search_result')
        with self.chunks.repo.transaction() as db:
            doc,_=self.chunks.documents.version(db,principal,ref.document_id,ref.version_id)
            if doc['active_version_id'] != ref.version_id:
                raise DomainError('inactive_search_evidence')
        return item

    def index(self, principal):
        self.principal(principal,True)
        with self.chunks.repo.transaction() as db:
            snapshot=self.store.eligible(db,principal.institution_id)
        if len(snapshot)>20000:
            raise DomainError('index_limit')
        for item in snapshot:
            self.validate(principal,item['chunk'])
        vectors=checked_vectors(self.embedding.embed([x['chunk']['text'] for x in snapshot]),len(snapshot),self.embedding.spec.dimension)
        for item in snapshot:
            self.validate(principal,item['chunk'])
        return self.store.publish(principal.institution_id,self.embedding.spec.model_dump(),snapshot,vectors)

    def search(self, principal, query, limit=5, mode='hybrid'):
        self.principal(principal)
        if not isinstance(query,str) or not query.strip() or len(query)>200 or len(query.split())>8 or not 1<=limit<=20 or mode not in ('keyword','vector','hybrid'):
            raise DomainError('invalid_search_query',400)
        keyword=self.chunks.search(principal,query,50) if mode in ('keyword','hybrid') else []
        vector=[]
        if mode in ('vector','hybrid'):
            q=checked_vectors(self.embedding.embed([query]),1,self.embedding.spec.dimension)[0]
            vector=self.store.candidates(principal.institution_id,self.embedding.spec.model_dump(),q,50)
        scores,items={},{}
        for ranked in (keyword,vector):
            seen=set()
            for rank,item in enumerate(ranked,1):
                self.validate(principal,item)
                ref=EvidenceRef.model_validate(item['evidence'])
                key=(ref.document_id,ref.version_id,ref.chunk_id)
                if key in seen:
                    raise DomainError('duplicate_search_result')
                seen.add(key);items[key]=item;scores[key]=scores.get(key,0)+1/(60+rank)
        keys=sorted(items,key=lambda k:(-scores[k],k))[:limit]
        return {'mode':mode,'test_only':True,'semantic_quality':'NOT_VERIFIED',
                'results':[{'chunk':self.validate(principal,items[k]),'rrf_score':scores[k]} for k in keys]}

    def answer(self, principal, question):
        self.principal(principal)
        if self.llm is None:
            raise DomainError('llm_not_configured',503)
        context=[r['chunk'] for r in self.search(principal,question)['results'] if r['chunk']['text']]
        # Offline double has no calibrated semantic relevance. Require lexical support as well.
        lexical={c['chunk_id'] for c in self.chunks.search(principal,question,50)}
        context=[c for c in context if c['chunk_id'] in lexical]
        output=Generation.model_validate(self.llm.generate(question,context))
        if (output.status=='candidate') != bool(output.claims):
            raise DomainError('invalid_generation_status',422)
        allowed={c['chunk_id']:c for c in context};claims=[]
        for claim in output.claims:
            if len(set(claim.chunk_ids))!=len(claim.chunk_ids) or any(k not in allowed for k in claim.chunk_ids):
                raise DomainError('unknown_citation',422)
            refs=[self.validate(principal,allowed[k])['evidence'] for k in claim.chunk_ids]
            # Structural linkage does not establish semantic entailment. Fail closed on invented prose.
            if not any(claim.text in allowed[k]['text'] for k in claim.chunk_ids):
                raise DomainError('unverified_generated_claim',422)
            claims.append({'text':claim.text,'evidence_refs':refs,'semantic_verification':'NOT_VERIFIED'})
        return {'status':output.status,'claims':claims,'generated_by':self.llm.model_id,
                'test_only':True,'content_origin':'generated_candidate','not_official_guidance':True}
