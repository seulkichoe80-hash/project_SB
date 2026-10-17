import hashlib
import io
import pdfplumber
from importlib.metadata import version
from ..errors import DomainError
from .contracts import make_block


class PDFParser:
    method = 'pdfplumber-' + version('pdfplumber') + '/phase2b-v1'

    def parse(self, data, document_id, version_id):
        digest = hashlib.sha256(data).hexdigest()
        blocks = []
        def add(selector, kind, text, page, bbox, **fields):
            block = make_block(document_id, version_id, digest, 'pdf', selector, kind, text,
                self.method, len(blocks), page=page, bbox=tuple(round(float(x), 4) for x in bbox), **fields)
            blocks.append(block)
            if len(blocks) > 20000:
                raise DomainError('extraction_block_limit')
            return block
        try:
            with pdfplumber.open(io.BytesIO(data)) as document:
                if not 0 < len(document.pages) <= 100:
                    raise DomainError('pdf_page_limit')
                for page in document.pages:
                    tables = page.find_tables()
                    events = [(table.bbox[1], table.bbox[0], 'table', table) for table in tables]
                    def outside_tables(obj):
                        if obj.get('object_type') != 'char':
                            return True
                        x = (obj['x0'] + obj['x1']) / 2
                        y = (obj['top'] + obj['bottom']) / 2
                        return not any(t.bbox[0] <= x <= t.bbox[2] and t.bbox[1] <= y <= t.bbox[3] for t in tables)
                    lines = page.filter(outside_tables).extract_text_lines(return_chars=False)
                    groups = []
                    for line in sorted(lines, key=lambda x: (x['top'], x['x0'])):
                        if not line['text'].strip():
                            continue
                        if groups:
                            previous = groups[-1][-1]
                            gap = line['top'] - previous['bottom']
                            height = previous['bottom'] - previous['top']
                            # Only adjacent, similarly aligned lines; paragraph boundaries remain heuristic.
                            merge = (-0.5 <= gap <= height * .65 and abs(line['x0'] - previous['x0']) <= 3)
                            if merge:
                                groups[-1].append(line)
                                continue
                        groups.append([line])
                    for group in groups:
                        bbox = (min(x['x0'] for x in group), min(x['top'] for x in group),
                                max(x['x1'] for x in group), max(x['bottom'] for x in group))
                        events.append((bbox[1], bbox[0], 'paragraph', (bbox, '\n'.join(x['text'] for x in group))))
                    if not events:
                        raise DomainError('pdf_page_no_extractable_content', 422)
                    for event_index, (_, _, kind, value) in enumerate(sorted(events, key=lambda x: (x[0], x[1]))):
                        selector = f'page:{page.page_number}:{kind}:{event_index}'
                        if kind == 'paragraph':
                            add(selector, kind, value[1], page.page_number, value[0])
                            continue
                        xs = sorted({round(c[i], 4) for c in value.cells for i in (0, 2)})
                        ys = sorted({round(c[i], 4) for c in value.cells for i in (1, 3)})
                        parent = add(selector, 'table', '', page.page_number, value.bbox,
                                     table_shape=(len(ys)-1, len(xs)-1))
                        texts = value.extract()
                        for r, row in enumerate(value.rows):
                            for c, bbox in enumerate(row.cells):
                                if bbox is None:
                                    continue  # Do not manufacture absent merged-cell placeholders.
                                x0, y0, x1, y1 = [round(v, 4) for v in bbox]
                                add(selector+f':cell:{r}:{c}', 'cell', texts[r][c] or '', page.page_number, bbox,
                                    parent_block_id=parent.block_id, row=ys.index(y0), column=xs.index(x0),
                                    row_span=ys.index(y1)-ys.index(y0), column_span=xs.index(x1)-xs.index(x0))
        except DomainError:
            raise
        except Exception:
            raise DomainError('pdf_parse_failure', 422) from None
        if not blocks or not any(b.text.strip() for b in blocks):
            raise DomainError('pdf_no_extractable_content', 422)
        return blocks
