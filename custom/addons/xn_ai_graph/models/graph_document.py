# -*- coding: utf-8 -*-
from odoo import models, api, _

import io
import logging
import re

import requests

_logger = logging.getLogger(__name__)

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"

# Refuse to download more than this. A policy document is a few hundred KB;
# anything far larger is a video, a database export or a scan, and pulling it
# into an Odoo worker's memory to find no text is the wrong trade.
MAX_DOWNLOAD_BYTES = 12 * 1024 * 1024

# Roughly 4000 tokens of context. Enough to answer from a policy section,
# small enough that a handful of reads does not dominate the monthly budget.
MAX_TEXT_CHARS = 16000

# How much text to return either side of a matched term when the caller says
# what it is looking for.
WINDOW_CHARS = 1200

# Extensions Graph will not usefully convert and that carry no text worth
# extracting. Checked before spending a download on them.
UNREADABLE_EXTENSIONS = (
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.ico',
    '.mp4', '.mov', '.avi', '.mkv', '.mp3', '.wav',
    '.zip', '.rar', '.7z', '.tar', '.gz', '.exe', '.dll',
)

PLAIN_TEXT_EXTENSIONS = ('.txt', '.md', '.csv', '.log', '.json', '.xml')


def _extract_pdf_text(data):
    """Text from PDF bytes, across both PyPDF2 APIs.

    Odoo pins PyPDF2 by Python version: 1.26.0 on 3.10 and 2.12.1 above it,
    and the two have incompatible APIs. Production runs 3.10, development
    here runs 3.12, so code written against either one alone works on one
    machine and fails on the other with no warning until a user tries it.
    """
    import PyPDF2

    stream = io.BytesIO(data)

    # PyPDF2 2.x / 3.x
    if hasattr(PyPDF2, 'PdfReader'):
        reader = PyPDF2.PdfReader(stream)
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or '')
            except Exception:  # noqa: BLE001 - one bad page should not lose the rest
                continue
        return '\n'.join(pages)

    # PyPDF2 1.x
    reader = PyPDF2.PdfFileReader(stream)
    pages = []
    for index in range(reader.getNumPages()):
        try:
            pages.append(reader.getPage(index).extractText() or '')
        except Exception:  # noqa: BLE001
            continue
    return '\n'.join(pages)


class GraphDocument(models.AbstractModel):
    """Read the contents of one document the current user can already open.

    Uses that user's delegated token, so a document they cannot open returns
    404 from Graph rather than text. As with search, there is no permission
    logic here on purpose.
    """

    _name = 'xn.graph.document'
    _description = 'Microsoft Graph Document Reader'

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    @api.model
    def _download(self, token, drive_id, item_id, as_pdf):
        """Bytes for one drive item, optionally converted to PDF by Graph.

        The conversion is what avoids a python-docx dependency: Graph will
        render Word, Excel and PowerPoint to PDF on its own, and Odoo already
        ships a PDF reader. One code path covers every Office format.
        """
        url = "%s/drives/%s/items/%s/content" % (GRAPH_ROOT, drive_id, item_id)
        params = {'format': 'pdf'} if as_pdf else None

        response = requests.get(
            url,
            headers={"Authorization": "Bearer %s" % token},
            params=params,
            timeout=60,
            stream=True,
        )
        if response.status_code >= 400:
            return None, response.status_code

        # Read with a ceiling rather than trusting Content-Length, which is
        # absent on the conversion endpoint.
        chunks = []
        total = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                response.close()
                return None, 'too_large'
        return b''.join(chunks), response.status_code

    # ------------------------------------------------------------------
    # Narrowing
    # ------------------------------------------------------------------

    @api.model
    def _relevant_passages(self, text, about):
        """The parts of `text` near the words in `about`.

        Head truncation is the obvious approach and the wrong one: the answer
        to "what is the notice period" is rarely in the first two pages of a
        handbook, so a truncated read confidently reports that the document
        does not say. Windowing around the search terms keeps the passage
        that actually matters.
        """
        if not about:
            return text[:MAX_TEXT_CHARS]

        terms = [t for t in re.split(r'\W+', about.lower()) if len(t) > 3]
        if not terms:
            return text[:MAX_TEXT_CHARS]

        lowered = text.lower()
        spans = []
        for term in terms:
            start = 0
            while True:
                found = lowered.find(term, start)
                if found == -1:
                    break
                spans.append((max(0, found - WINDOW_CHARS // 2),
                              min(len(text), found + WINDOW_CHARS // 2)))
                start = found + len(term)
                if len(spans) > 40:
                    break

        if not spans:
            return text[:MAX_TEXT_CHARS]

        # Merge overlapping windows so a dense section is returned once, in
        # order, rather than as a dozen near-identical fragments.
        spans.sort()
        merged = [spans[0]]
        for start, end in spans[1:]:
            if start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))

        out = []
        length = 0
        for start, end in merged:
            piece = text[start:end]
            if length + len(piece) > MAX_TEXT_CHARS:
                out.append(piece[:MAX_TEXT_CHARS - length])
                break
            out.append(piece)
            length += len(piece)
        return '\n[...]\n'.join(out)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    @api.model
    def read_document(self, document_id, about=None):
        """Return the text of one document, narrowed to what was asked about.

        `document_id` is the opaque value search_documents returns, not a URL:
        parsing a SharePoint webUrl back into drive and item identifiers is
        guesswork, and carrying the identifiers through from the search that
        produced them is not.
        """
        token = self.env['xn.graph.token'].get_valid_token()
        if not token:
            return {"status": "not_connected",
                    "message": "This user has not connected their Microsoft "
                               "documents."}

        if not document_id or ':' not in str(document_id):
            return {"status": "error",
                    "message": "That document reference is not one returned "
                               "by a document search."}
        drive_id, item_id = str(document_id).split(':', 1)

        meta_response = requests.get(
            "%s/drives/%s/items/%s" % (GRAPH_ROOT, drive_id, item_id),
            headers={"Authorization": "Bearer %s" % token},
            timeout=30,
        )
        if meta_response.status_code == 404:
            return {"status": "not_found",
                    "message": "That document is no longer available to this "
                               "user."}
        if meta_response.status_code >= 400:
            _logger.warning("xn_ai_graph: item lookup returned %s",
                            meta_response.status_code)
            return {"status": "error",
                    "message": "That document could not be opened."}

        meta = meta_response.json()
        name = meta.get('name') or ''
        lowered = name.lower()

        if lowered.endswith(UNREADABLE_EXTENSIONS):
            return {"status": "unreadable",
                    "title": name,
                    "message": "That file is an image, media or archive file "
                               "and has no text to read."}

        is_plain = lowered.endswith(PLAIN_TEXT_EXTENSIONS)
        data, code = self._download(token, drive_id, item_id, as_pdf=not is_plain)

        if code == 'too_large':
            return {"status": "too_large",
                    "title": name,
                    "message": "That document is too large to read."}
        if data is None:
            _logger.info("xn_ai_graph: download returned %s for %s", code, name)
            return {"status": "error",
                    "title": name,
                    "message": "That document could not be read. It may be a "
                               "format that cannot be converted to text."}

        try:
            if is_plain:
                text = data.decode('utf-8', errors='replace')
            else:
                text = _extract_pdf_text(data)
        except Exception:  # noqa: BLE001
            _logger.exception("xn_ai_graph: extraction failed for %s", name)
            return {"status": "error",
                    "title": name,
                    "message": "That document could not be read as text."}

        text = re.sub(r'\n{3,}', '\n\n', (text or '').strip())
        if not text:
            return {"status": "no_text",
                    "title": name,
                    "link": meta.get('webUrl'),
                    "message": "That document contains no extractable text. "
                               "It is most likely a scan, which would need "
                               "OCR."}

        passage = self._relevant_passages(text, about)
        return {
            "status": "ok",
            "title": name,
            "link": meta.get('webUrl'),
            "truncated": len(passage) < len(text),
            "content": passage,
        }
