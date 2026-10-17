import io
import re
import zipfile
from pathlib import PurePosixPath
from defusedxml import ElementTree
from .errors import DomainError

MAX_BYTES = 20 * 1024 * 1024


def inspect_file(name: str, mime: str, data: bytes) -> tuple[str, str]:
    if not name or len(name) > 200 or any(c in name for c in '/\\:\x00') or any(ord(c) < 32 for c in name):
        raise DomainError('invalid_filename', 400)
    if not data or len(data) > MAX_BYTES:
        raise DomainError('file_size_limit', 413)
    ext = PurePosixPath(name).suffix.lower()
    if ext not in ('.pdf', '.hwpx'):
        raise DomainError('unsupported_extension', 415)
    expected = 'application/pdf' if ext == '.pdf' else 'application/hwp+zip'
    if mime.split(';')[0].strip().lower() not in (expected, 'application/octet-stream'):
        raise DomainError('mime_mismatch', 415)
    if ext == '.pdf':
        # Conservative structural admission, NOT a full PDF parser or malware scan.
        if not re.match(rb'%PDF-1\.[0-9]', data) or not data.rstrip().endswith(b'%%EOF'):
            raise DomainError('invalid_pdf', 415)
        if not all(token in data for token in (b'/Catalog', b'/Pages', b'startxref')):
            raise DomainError('invalid_pdf', 415)
        # Phase 2A supports ordinary classic-xref PDFs; compressed xref streams are deferred.
        tail = re.search(rb'startxref\s+(\d+)\s+%%EOF\s*$', data)
        if not tail or data[int(tail[1]):int(tail[1])+4] != b'xref':
            raise DomainError('invalid_or_unsupported_pdf_xref', 415)
        xref = data[int(tail[1]):tail.start()]
        entries = re.findall(rb'(\d{10}) (\d{5}) n', xref)
        if not entries or b'/Root' not in xref or b'trailer' not in xref:
            raise DomainError('invalid_pdf_xref', 415)
        for offset, generation in entries:
            if not re.match(rb'\d+ ' + str(int(generation)).encode() + rb' obj\b', data[int(offset):]):
                raise DomainError('invalid_pdf_object_offset', 415)
        if any(token in data for token in (b'/JavaScript', b'/JS', b'/Launch', b'/EmbeddedFile', b'/Encrypt')):
            raise DomainError('unsupported_pdf_features', 415)
        return 'pdf', expected
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            names = [e.filename for e in entries]
            if len(entries) > 1000 or len(names) != len(set(names)):
                raise ValueError()
            if sum(e.file_size for e in entries) > 200 * 1024 * 1024:
                raise ValueError()
            for entry in entries:
                parts = PurePosixPath(entry.filename).parts
                if (entry.filename.startswith('/') or '\\' in entry.filename or ':' in entry.filename
                    or '..' in parts or entry.flag_bits & 1
                    or entry.file_size > max(entry.compress_size, 1) * 100):
                    raise ValueError()
            if archive.read('mimetype') != b'application/hwp+zip':
                raise ValueError()
            if not {'Contents/content.hpf', 'Contents/header.xml'}.issubset(names):
                raise ValueError()
            sections = [n for n in names if re.fullmatch(r'Contents/section\d+\.xml', n)]
            if not sections:
                raise ValueError()
            for name_in_zip in names:
                if name_in_zip.endswith(('.xml', '.hpf')):
                    ElementTree.fromstring(archive.read(name_in_zip))
            if archive.testzip() is not None:
                raise ValueError()
    except Exception:
        raise DomainError('invalid_hwpx', 415) from None
    return 'hwpx', expected
