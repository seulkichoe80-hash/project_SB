"""Project-authored 2-page PDF bytes. No private inputs or redistributed font files."""
def synthetic_pdf(label='Public synthetic manual', merged_header=False, blank_second_page=False):
    def text(x, y, value):
        value = value.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        return f'BT /F1 12 Tf {x} {y} Td ({value}) Tj ET\n'
    first = text(50,750,label) + text(50,700,'Prepare the request.') + text(50,686,'Attach the public form.')
    first += text(50,640,'Send to the synthetic reviewer.')
    first += ''.join(f'{x} 400 m {x} {440 if merged_header and x == 250 else 480} l S\n' for x in (50,250,450))
    first += ''.join(f'50 {y} m 450 {y} l S\n' for y in (400,440,480))
    first += text(60,455,'Stage')+text(260,455,'Form')+text(60,415,'Submit')+text(260,415,'Request')
    second = text(50,740,'Second page evidence') + text(50,680,'Keep the original unchanged.')
    if blank_second_page:
        second = ''
    streams = [first.encode('ascii'), second.encode('ascii')]
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 500 800] /Resources << /Font << /F1 5 0 R >> >> /Contents 6 0 R >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 500 800] /Resources << /Font << /F1 5 0 R >> >> /Contents 7 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    objects += [b'<< /Length '+str(len(s)).encode()+b' >>\nstream\n'+s+b'endstream' for s in streams]
    data = b'%PDF-1.4\n'
    offsets = []
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f'{index} 0 obj\n'.encode()+obj+b'\nendobj\n'
    start = len(data)
    data += f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode()
    data += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets)
    return data+f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()
