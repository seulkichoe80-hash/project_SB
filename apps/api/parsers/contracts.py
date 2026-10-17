import hashlib
import json
from typing import Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field, model_validator
from ..errors import DomainError


class Anchor(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    document_id: str
    version_id: str
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    kind: Literal['pdf', 'hwpx']
    selector: str
    page: int | None = Field(default=None, ge=1)
    bbox: tuple[float, float, float, float] | None = None
    part: str | None = None
    xml_path: tuple[int, ...] | None = None
    tag: str | None = None

    @model_validator(mode='after')
    def location(self):
        if self.kind == 'pdf':
            if self.page is None or self.bbox is None or self.part is not None or self.xml_path is not None:
                raise ValueError('PDF requires page and bbox only')
            x0, y0, x1, y1 = self.bbox
            if not (0 <= x0 < x1 and 0 <= y0 < y1):
                raise ValueError('invalid bbox')
        elif (self.page is not None or self.bbox is not None or self.part is None
              or self.xml_path is None or self.tag is None or any(i < 0 for i in self.xml_path)):
            raise ValueError('HWPX requires XML location; page/visual coordinates unknown')
        return self


class Block(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    document_id: str
    version_id: str
    block_id: str
    block_type: Literal['paragraph', 'heading', 'table', 'cell', 'image']
    text: str
    source_anchor: Anchor
    extraction_method: str
    order_index: int = Field(ge=0)
    verification_status: Literal['structural_only'] = 'structural_only'
    semantic_verification: Literal['NOT_VERIFIED'] = 'NOT_VERIFIED'
    source_kind: Literal['original_text', 'original_image', 'original_structure']
    order_basis: Literal['geometric_heuristic', 'xml_spine_preorder']
    visual_order_verification: Literal['NOT_VERIFIED'] = 'NOT_VERIFIED'
    parent_block_id: str | None = None
    row: int | None = Field(default=None, ge=0)
    column: int | None = Field(default=None, ge=0)
    row_span: int | None = Field(default=None, ge=1)
    column_span: int | None = Field(default=None, ge=1)
    table_shape: tuple[int, int] | None = None
    asset_ref: str | None = None
    asset_sha256: str | None = None
    context_relation: Literal['xml_containment'] | None = None

    @model_validator(mode='after')
    def table_bounds(self):
        if self.table_shape is not None:
            rows, columns = self.table_shape
            if not (1 <= rows <= 1000 and 1 <= columns <= 1000 and rows * columns <= 20000):
                raise ValueError('table grid limit')
        return self


class ParserAdapter(Protocol):
    method: str
    def parse(self, data: bytes, document_id: str, version_id: str) -> list[Block]: ...


def make_block(document_id, version_id, digest, kind, selector, block_type, text, method, index, **fields):
    location = {key: fields.pop(key) for key in list(fields) if key in ('page','bbox','part','xml_path','tag')}
    anchor = Anchor(document_id=document_id, version_id=version_id, sha256=digest,
                    kind=kind, selector=selector, **location)
    key = json.dumps(anchor.model_dump(mode='json'), sort_keys=True, separators=(',', ':'))
    return Block(document_id=document_id, version_id=version_id,
                 block_id=hashlib.sha256(key.encode()).hexdigest(), block_type=block_type,
                 text=text, source_anchor=anchor, extraction_method=method, order_index=index,
                 source_kind='original_image' if block_type == 'image' else
                    ('original_structure' if block_type == 'table' else 'original_text'),
                 order_basis='geometric_heuristic' if kind == 'pdf' else 'xml_spine_preorder', **fields)


def validate_batch(blocks: list[Block], canonical: list[Block], document_id, version_id):
    """Re-extraction is structural evidence checking, NOT semantic/visual proof."""
    expected = {b.block_id: b for b in canonical}
    if not blocks or len(blocks) > 20000 or len(blocks) != len(expected):
        raise DomainError('invalid_extraction_batch')
    seen = set()
    for index, block in enumerate(blocks):
        if (block.document_id != document_id or block.version_id != version_id
            or block.order_index != index or block.block_id in seen
            or block.block_id not in expected or block != expected[block.block_id]):
            raise DomainError('invalid_source_anchor_or_block')
        if block.parent_block_id and block.parent_block_id not in seen:
            raise DomainError('invalid_parent_block')
        seen.add(block.block_id)
