"""Create a complete synthetic HWPX through python-hwpx; never edit supplied originals."""
from pathlib import Path
from hwpx import HwpxDocument
import json,hashlib,struct,zlib,importlib.metadata

root=Path(__file__).resolve().parents[2]
dest=root/'tests/fixtures/synthetic';dest.mkdir(parents=True,exist_ok=True)
target=dest/'procedure-v2.hwpx'
if target.exists():raise SystemExit('Refusing to overwrite existing fixture')
def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
image=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\x10\x80\xff'))+chunk(b'IEND',b'')
doc=HwpxDocument.new()
doc.add_paragraph('합성기관 A 시험 업무 매뉴얼')
doc.add_paragraph('1. 신청서를 작성한다.')
table=doc.add_table(rows=2,cols=2)
for r,c,text in [(0,0,'단계'),(0,1,'필요 서류'),(1,0,'신청'),(1,1,'합성 신청서')]:table.set_cell_text(r,c,text)
doc.add_paragraph('그림 앞 설명: 다음 그림은 구조 검증용 픽셀이다.')
doc.add_picture(image,'png',width_mm=10,height_mm=10)
doc.add_paragraph('2. 담당자가 신청서를 확인한다.')
validation=doc.validate()
doc.save_to_path(target)
reopened=HwpxDocument.open(target)
validation2=reopened.validate()
info={'id':'hwpx-synthetic-v2','file':'procedure-v2.hwpx','kind':'synthetic','tenant':'A','version':'v2','generator':'python-hwpx','generator_version':importlib.metadata.version('python-hwpx'),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'validation_before_save':str(validation),'validation_after_reopen':str(validation2),'visual_hancom_validation':'NOT_RUN','license':'python-hwpx Apache-2.0 template; project-authored text/pixel; no private source documents','expected_text':['합성기관 A 시험 업무 매뉴얼','1. 신청서를 작성한다.','단계','필요 서류','신청','합성 신청서','그림 앞 설명: 다음 그림은 구조 검증용 픽셀이다.','2. 담당자가 신청서를 확인한다.']}
(dest/'hwpx-manifest-v2.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(info,ensure_ascii=False,indent=2))
