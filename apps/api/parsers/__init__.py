from .pdf import PDFParser
from .hwpx import HWPXParser


def default_parsers():
    return {'pdf': PDFParser(), 'hwpx': HWPXParser()}
