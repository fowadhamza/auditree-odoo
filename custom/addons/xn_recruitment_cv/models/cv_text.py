# -*- coding: utf-8 -*-
"""Plain text out of a CV file, using only what the venv already has.

PDF goes through PyPDF2, an Odoo requirement (1.26 on the production venv).
pdfminer is tried first when it happens to be installed, because its word
spacing is much better, but it is not required: adding a package means a venv
change on production, and the venv rebuild is the deploy step that has broken
that server before. DOCX is a zip of XML and needs no library at all.

Scanned CVs (a picture of a page) have no text layer and come back empty;
the caller treats that as "fill in by hand".
"""
import io
import logging
import re
import zipfile

from lxml import etree

_logger = logging.getLogger(__name__)

WORD_NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
DOCX_MIMETYPE = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


def is_readable(attachment):
    """True for the file types extract_text() can read."""
    name = (attachment.name or '').lower()
    mimetype = attachment.mimetype or ''
    return (mimetype in ('application/pdf', DOCX_MIMETYPE, 'text/plain')
            or name.endswith(('.pdf', '.docx', '.txt')))


def extract_text(data, mimetype, filename):
    """Return the text of a PDF, DOCX or plain-text file, or '' if unreadable.

    A broken or password-protected file is "no text", not an error: one bad
    attachment must not stop the scheduled job from reading the next CV.
    """
    if not data:
        return ''
    name = (filename or '').lower()
    try:
        if data.startswith(b'%PDF-'):
            text = _pdf_text(data)
        elif name.endswith('.docx') or mimetype == DOCX_MIMETYPE:
            text = _docx_text(data)
        elif name.endswith('.txt') or mimetype == 'text/plain':
            text = data.decode('utf-8', errors='replace')
        else:
            return ''
    except Exception as exc:  # noqa: BLE001 - see docstring
        _logger.warning("xn_recruitment_cv: could not read text from %s: %s", filename, exc)
        return ''
    return _tidy(text)


def _pdf_text(data):
    try:
        from pdfminer.high_level import extract_text as pdfminer_extract_text
    except ImportError:
        pdfminer_extract_text = None
    if pdfminer_extract_text:
        return pdfminer_extract_text(io.BytesIO(data))

    from odoo.tools.pdf import PdfFileReader
    reader = PdfFileReader(io.BytesIO(data), strict=False)
    # PyPDF2 1.x says isEncrypted, 2.x is_encrypted. Many CVs are "encrypted"
    # with an empty password only to stop copying; that still opens.
    if getattr(reader, 'is_encrypted', None) or getattr(reader, 'isEncrypted', False):
        reader.decrypt('')
    pages = []
    for page in reader.pages:
        extract = getattr(page, 'extract_text', None) or page.extractText
        pages.append(extract() or '')
    return '\n'.join(pages)


def _docx_text(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        xml = archive.read('word/document.xml')
    # The file comes from a stranger: no entity expansion, no network.
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    root = etree.fromstring(xml, parser=parser)
    lines = []
    # Paragraphs include those inside tables and text boxes, which is where
    # CV templates tend to put contact details.
    for paragraph in root.iter(WORD_NS + 'p'):
        text = ''.join(node.text or '' for node in paragraph.iter(WORD_NS + 't'))
        if text.strip():
            lines.append(text)
    return '\n'.join(lines)


def _tidy(text):
    text = text.replace('\x00', '')
    text = re.sub(r'[ \t\r\f\v]+', ' ', text)
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    return text.strip()
