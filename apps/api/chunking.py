"""Deterministic structural chunking. No tokens, models or inferred business facts."""
import hashlib
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .parsers.contracts import Anchor, Block
from .errors import DomainError

METHOD = 'structural-v1'
MAX_CHUNKS = 20000


class ChunkConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    max_chars: int = Field(default=800,ge=64,le=4000)
    context_chars: int = Field(default=400,ge=0,le=2000)


class Span(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    block_id: str
    source_anchor: Anchor
    role: Literal['primary','title_context','table_context','first_row_context','image_parent_context']
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    quote: str
    source_kind: Literal['original_text','original_image','original_structure']


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    organization_id: str
    document_id: str
    version_id: str
    chunk_id: str
    source_block_ids: list[str]
    source_anchor: list[Anchor]
    spans: list[Span]
    verification_status: Literal['structural_only'] = 'structural_only'
    semantic_verification: Literal['NOT_VERIFIED'] = 'NOT_VERIFIED'


class Chunk(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    chunk_id: str
    kind: Literal['paragraph','heading','table_row','image']
    text: str
    order_index: int
    grid: list[dict]
    context_truncated: bool
    evidence: EvidenceRef


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def build_chunks(blocks: list[Block], organization_id: str, config: ChunkConfig):
    if not blocks:
        raise DomainError('no_source_blocks')
    source = {b.block_id:b for b in blocks}
    if len(source) != len(blocks) or len({(b.document_id,b.version_id) for b in blocks}) != 1:
        raise DomainError('mixed_source_blocks')
    def cell_ancestor(block):
        parent, seen = block.parent_block_id, set()
        while parent:
            if parent in seen or parent not in source:
                raise DomainError('invalid_block_hierarchy')
            seen.add(parent)
            if source[parent].block_type == 'cell':
                return True
            parent = source[parent].parent_block_id
        return False
    def span(block,role='primary',start=0,end=None):
        end = len(block.text) if end is None else end
        return Span(block_id=block.block_id,source_anchor=block.source_anchor,role=role,
                    start=start,end=end,quote=block.text[start:end],source_kind=block.source_kind)
    chunks, heading = [], None
    table_cells = {}
    for block in blocks:
        if block.block_type == 'cell':
            table_cells.setdefault(block.parent_block_id,[]).append(block)

    def emit(kind,primary,contexts=(),grid=()):
        context, budget, truncated = [], config.context_chars, False
        primary_ids = {s.block_id for s in primary}
        for block,role in contexts:
            if block.block_id in primary_ids:
                continue
            end = min(len(block.text),budget)
            if block.text and end == 0:
                truncated = True
                continue
            context.append(span(block,role,end=end))
            budget -= end
            truncated |= end < len(block.text)
        spans = primary+context
        text = '\n'.join(s.quote for s in primary if s.source_kind == 'original_text')
        key = digest({'method':METHOD,'config':config.model_dump(),'organization':organization_id,
                      'spans':[s.model_dump(mode='json') for s in spans],'kind':kind})
        ids = list(dict.fromkeys(s.block_id for s in spans))
        ref = EvidenceRef(organization_id=organization_id,document_id=blocks[0].document_id,
            version_id=blocks[0].version_id,chunk_id=key,source_block_ids=ids,
            source_anchor=[source[i].source_anchor for i in ids],spans=spans)
        chunks.append(Chunk(chunk_id=key,kind=kind,text=text,order_index=len(chunks),grid=list(grid),
                            context_truncated=truncated,evidence=ref))
        if len(chunks)>MAX_CHUNKS:
            raise DomainError('chunk_limit')

    for block in blocks:
        if block.block_type in ('paragraph','heading'):
            if cell_ancestor(block) or not block.text.strip():
                continue  # Cell aggregate is emitted once; do not duplicate child paragraphs.
            if block.block_type == 'heading':
                heading = block
            context = [(heading,'title_context')] if heading and heading.block_id != block.block_id else []
            for start in range(0,len(block.text),config.max_chars):
                emit(block.block_type,[span(block,start=start,end=min(start+config.max_chars,len(block.text)))],context)
        elif block.block_type == 'table':
            cells = sorted(table_cells.get(block.block_id,[]),key=lambda b:(b.row,b.column))
            first_row = [(c,'first_row_context') for c in cells if c.row == 0]
            for cell in cells:
                grid = [{'table_block_id':block.block_id,'table_shape':block.table_shape,
                         'cell_block_id':cell.block_id,'row':cell.row,'column':cell.column,
                         'row_span':cell.row_span,'column_span':cell.column_span}]
                # A cell fragment is the smallest row unit: no row/column/span metadata is lost.
                contexts = [(block,'table_context')]+([(heading,'title_context')] if heading else [])+first_row
                for start in range(0,max(1,len(cell.text)),config.max_chars):
                    emit('table_row',[span(cell,start=start,end=min(start+config.max_chars,len(cell.text)))],contexts,grid)
        elif block.block_type == 'image':
            parent = source.get(block.parent_block_id)
            contexts = [(parent,'image_parent_context')] if parent and block.context_relation == 'xml_containment' else []
            emit('image',[span(block)],contexts)
    return chunks
