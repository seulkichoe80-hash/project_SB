"""Offline adapter contracts. Test doubles are never semantic-model evidence."""
import hashlib
import math
from typing import Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field
from .errors import DomainError


class EmbeddingSpec(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    provider: str = 'synthetic'
    model: str = 'hash-character-v1'
    dimension: int = Field(default=64, ge=4, le=4096)
    normalization: Literal['l2'] = 'l2'
    metric: Literal['cosine'] = 'cosine'
    test_only: bool = True


class EmbeddingAdapter(Protocol):
    spec: EmbeddingSpec
    def embed(self, texts: list[str]) -> list[list[float]]: ...


def checked_vectors(vectors, count, dimension):
    if len(vectors) != count:
        raise DomainError('embedding_count_mismatch', 422)
    result = []
    for row in vectors:
        if len(row) != dimension or any(isinstance(x, bool) or not isinstance(x, (int,float)) or not math.isfinite(x) for x in row):
            raise DomainError('invalid_embedding', 422)
        norm = math.sqrt(sum(x*x for x in row))
        if not math.isfinite(norm) or norm <= 0:
            raise DomainError('invalid_embedding', 422)
        result.append([x/norm for x in row])
    return result


class DeterministicEmbedding:
    def __init__(self, dimension=64):
        self.spec = EmbeddingSpec(dimension=dimension)

    def embed(self, texts):
        rows = []
        for text in texts:
            row = [0.0]*self.spec.dimension
            for char in text.casefold():
                if not char.isspace():
                    h = hashlib.sha256(char.encode()).digest()
                    row[int.from_bytes(h[:4],'big') % len(row)] += 1.0
            if not any(row):
                row[0] = 1.0
            rows.append(row)
        return checked_vectors(rows,len(texts),self.spec.dimension)


class Claim(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    text: str = Field(min_length=1,max_length=4000)
    chunk_ids: list[str] = Field(min_length=1,max_length=20)


class Generation(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    status: Literal['candidate','insufficient_evidence']
    claims: list[Claim] = Field(default_factory=list,max_length=20)


class LLMAdapter(Protocol):
    model_id: str
    test_only: bool
    def generate(self, question: str, context: list[dict]) -> Generation: ...


class ExtractiveTestLLM:
    model_id = 'synthetic-extractive-v1'
    test_only = True
    def generate(self, question, context):
        if not context:
            return Generation(status='insufficient_evidence')
        item = next((c for c in context if c['text']),None)
        return Generation(status='candidate',claims=[Claim(text=item['text'],chunk_ids=[item['chunk_id']])]) if item else Generation(status='insufficient_evidence')


class HybridSearch(Protocol):
    def search(self, principal, query: str, limit: int = 5, mode: str = 'hybrid') -> dict: ...
