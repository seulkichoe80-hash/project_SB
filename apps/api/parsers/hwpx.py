import hashlib
import io
import posixpath
import re
import zipfile
from defusedxml import ElementTree as ET
from ..errors import DomainError
from ..formats import inspect_file
from .contracts import make_block


def local(node):
    return node.tag.rsplit('}', 1)[-1]


class HWPXParser:
    method = 'hwpx-defusedxml/phase2b-v1'

    def parse(self, data, document_id, version_id):
        inspect_file('input.hwpx', 'application/hwp+zip', data)
        digest = hashlib.sha256(data).hexdigest()
        blocks = []
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
                package = ET.fromstring(archive.read('Contents/content.hpf'))
                def resolve(href):
                    if not href or ':' in href or '\\' in href or href.startswith('/') or '..' in href.split('/'):
                        raise DomainError('unsafe_hwpx_relationship', 422)
                    for candidate in (posixpath.normpath(posixpath.join('Contents', href)), href):
                        if candidate in names:
                            return candidate
                    raise DomainError('missing_hwpx_relationship', 422)
                manifest = {}
                for item in package.iter():
                    if local(item) == 'item':
                        key = item.attrib['id']
                        if key in manifest:
                            raise DomainError('duplicate_hwpx_relationship', 422)
                        manifest[key] = resolve(item.attrib.get('href'))
                parts = [manifest[node.attrib['idref']] for node in package.iter() if local(node) == 'itemref']
                sections = [p for p in parts if p.startswith('Contents/section') and p.endswith('.xml')]
                if not sections or len(sections) != len(set(sections)):
                    raise DomainError('invalid_hwpx_spine', 422)
                header = ET.fromstring(archive.read('Contents/header.xml'))
                heading_styles = {e.attrib.get('id') for e in header.iter() if local(e) == 'style'
                    and any(re.fullmatch(r'(heading\s*\d*|title|subtitle|제목\s*\d*)', label.strip(), re.I)
                            for label in (e.attrib.get('name',''), e.attrib.get('engName','')))}
                def direct_text(node):
                    # Text belonging to this paragraph/cell only; nested tables have separate blocks.
                    result = []
                    def visit(child, in_text=False):
                        if local(child) in ('tbl', 'pic', 'header', 'footer', 'footNote', 'endNote'):
                            return
                        if local(child) == 't':
                            result.append(child.text or '')
                            in_text = True
                        elif local(child) == 'p' and local(node) == 'tc' and result and result[-1] != '\n':
                            result.append('\n')
                        elif local(child) == 'lineBreak':
                            result.append('\n')
                        elif local(child) == 'tab':
                            result.append('\t')
                        for sub in child:
                            visit(sub, in_text)
                            if in_text and sub.tail:
                                result.append(sub.tail)
                    visit(node)
                    return ''.join(result)
                for part in sections:
                    tree = ET.fromstring(archive.read(part))
                    if local(tree) != 'sec':
                        raise DomainError('invalid_hwpx_section', 422)
                    def walk(node, path, parent=None, table=None):
                        kind = local(node)
                        fields = {}
                        block_type = None
                        text = ''
                        if kind == 'p':
                            block_type = 'heading' if node.attrib.get('styleIDRef') in heading_styles else 'paragraph'
                            text = direct_text(node)
                        elif kind == 'tbl':
                            block_type = 'table'
                            fields['table_shape'] = (int(node.attrib['rowCnt']), int(node.attrib['colCnt']))
                        elif kind == 'tc':
                            block_type = 'cell'
                            addr = next(x for x in node if local(x) == 'cellAddr')
                            span = next(x for x in node if local(x) == 'cellSpan')
                            fields.update(row=int(addr.attrib['rowAddr']), column=int(addr.attrib['colAddr']),
                                row_span=int(span.attrib['rowSpan']), column_span=int(span.attrib['colSpan']))
                            parent = table
                            text = direct_text(node)
                        elif kind == 'img':
                            block_type = 'image'
                            asset = manifest.get(node.attrib.get('binaryItemIDRef'))
                            if asset is None:
                                raise DomainError('missing_hwpx_image', 422)
                            fields.update(asset_ref=asset, asset_sha256=hashlib.sha256(archive.read(asset)).hexdigest(),
                                          context_relation='xml_containment' if parent else None)
                        if block_type:
                            block = make_block(document_id, version_id, digest, 'hwpx',
                                part+'#/'+'/'.join(map(str,path)), block_type, text, self.method, len(blocks),
                                part=part, xml_path=path, tag=node.tag, parent_block_id=parent, **fields)
                            blocks.append(block)
                            if len(blocks) > 20000:
                                raise DomainError('extraction_block_limit')
                            parent = block.block_id
                            if kind == 'tbl':
                                table = block.block_id
                        for index, child in enumerate(node):
                            walk(child, path+(index,), parent, table)
                    walk(tree, ())
        except DomainError:
            raise
        except Exception:
            raise DomainError('hwpx_parse_failure', 422) from None
        if not blocks:
            raise DomainError('hwpx_no_extractable_content', 422)
        tables = {b.block_id:b for b in blocks if b.block_type == 'table'}
        occupied = {}
        occupied_count = 0
        for block in blocks:
            if block.block_type != 'cell':
                continue
            table = tables.get(block.parent_block_id)
            if table is None or block.row + block.row_span > table.table_shape[0] or block.column + block.column_span > table.table_shape[1]:
                raise DomainError('invalid_hwpx_cell_grid', 422)
            used = occupied.setdefault(table.block_id, set())
            cells = {(r,c) for r in range(block.row,block.row+block.row_span)
                     for c in range(block.column,block.column+block.column_span)}
            if used & cells:
                raise DomainError('overlapping_hwpx_cells', 422)
            used.update(cells)
            occupied_count += len(cells)
            if occupied_count > 20000:
                raise DomainError('hwpx_table_grid_limit', 422)
        return blocks
