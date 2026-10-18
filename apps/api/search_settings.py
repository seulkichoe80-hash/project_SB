"""Server-only opt-in lexical search configuration. No provider or client activation."""
import os
import unicodedata
from pydantic import BaseModel,ConfigDict,Field


class SearchSettings(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)
    scored_or_enabled:bool=False
    max_scanned_chunks:int=Field(default=20000,ge=1,le=20000)
    max_scanned_bytes:int=Field(default=33554432,ge=1024,le=67108864)

    @classmethod
    def from_environment(cls):
        value=os.environ.get('SB_ENABLE_SCORED_OR_SEARCH','0')
        if value not in ('0','1'):raise ValueError('invalid_scored_or_feature_flag')
        return cls(scored_or_enabled=value=='1')


def normalize_search(text):
    value=unicodedata.normalize('NFKC',text).casefold()
    return ' '.join(''.join(' ' if unicodedata.category(c).startswith('P') else c for c in value).split())


def scored_terms(query):
    if (not isinstance(query,str) or not query.strip() or len(query)>2000 or len(query.split())>128
            or any(len(t)>200 for t in query.split())):raise ValueError('scored_or_query_limit')
    value=normalize_search(query);terms=list(dict.fromkeys(value.split()))
    if len(value)>4000 or len(value.split())>128 or any(len(t)>200 for t in terms):raise ValueError('scored_or_query_limit')
    return terms
