# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

import logging
import re

import requests

_logger = logging.getLogger(__name__)

GRAPH_SEARCH_URL = "https://graph.microsoft.com/v1.0/search/query"

# Two or three hits, not ten. Document text is the one input that scales with
# content size rather than user count, so it is what actually moves the token
# bill -- and a model handed ten documents tends to blend them.
DEFAULT_HIT_COUNT = 3

# Graph returns summaries with <c0> markers around the matched terms.
HIT_HIGHLIGHT_RE = re.compile(r'</?c\d+>')


class GraphSearch(models.AbstractModel):
    """Document search over Microsoft Graph, as the requesting user.

    The token used is that user's own delegated token, so SharePoint applies
    its own permissions to every query. A user finds exactly what they could
    find in SharePoint's search box and nothing more. There is no permission
    logic in this file, deliberately: writing any would mean a second,
    weaker copy of a decision SharePoint already makes correctly.
    """

    _name = 'xn.graph.search'
    _description = 'Microsoft Graph Document Search'

    @api.model
    def _clean_summary(self, summary):
        if not summary:
            return ''
        return HIT_HIGHLIGHT_RE.sub('', summary).strip()

    @api.model
    def _scoped_query(self, query_string):
        """Optionally restrict the search to configured sites.

        xn_ai_graph.search_sites holds a comma separated list of site paths,
        e.g. "policies,hr-portal". Left empty, the search covers everything
        the user can see, which is the right default for a small tenant and
        the wrong one once there are many sites.
        """
        sites = self.env['ir.config_parameter'].sudo().get_param(
            'xn_ai_graph.search_sites')
        if not sites:
            return query_string
        clauses = ' OR '.join(
            'site:"%s"' % site.strip()
            for site in sites.split(',') if site.strip())
        if not clauses:
            return query_string
        return '%s (%s)' % (query_string, clauses)

    @api.model
    def search_documents(self, query_string, size=DEFAULT_HIT_COUNT):
        """Search the current user's accessible documents.

        Returns a dict the assistant can hand straight to the model. Never
        raises for an expected condition: not connected, no results and a
        refused call are all ordinary outcomes the model should describe to
        the user, not exceptions that lose the conversation.
        """
        token = self.env['xn.graph.token'].get_valid_token()
        if not token:
            return {
                "status": "not_connected",
                "message": "This user has not connected their Microsoft "
                           "documents. They can do so from their Odoo "
                           "preferences, under Assistant.",
            }

        # Ask for more than we intend to show: folders and duplicates are
        # filtered out after the fact, and asking for three often leaves one
        # once they are gone.
        wanted = max(1, min(int(size or DEFAULT_HIT_COUNT), 5))
        body = {
            "requests": [{
                "entityTypes": ["driveItem"],
                "query": {"queryString": self._scoped_query(query_string)},
                "from": 0,
                "size": wanted * 4,
                # Without an explicit list Graph omits the file facet, and
                # without that there is no way to tell a document from a
                # folder.
                "fields": [
                    "name", "webUrl", "file", "parentReference",
                    "lastModifiedDateTime",
                ],
            }]
        }

        try:
            response = requests.post(
                GRAPH_SEARCH_URL,
                headers={"Authorization": "Bearer %s" % token,
                         "Content-Type": "application/json"},
                json=body,
                timeout=30,
            )
        except requests.RequestException:
            _logger.exception("xn_ai_graph: search request failed")
            return {"status": "error",
                    "message": "Document search is unavailable right now."}

        if response.status_code == 401:
            # The token was accepted by our own expiry check but rejected by
            # Graph, which means it was revoked rather than merely expired.
            _logger.info("xn_ai_graph: Graph rejected the token for %s",
                         self.env.user.login)
            return {"status": "not_connected",
                    "message": "The Microsoft connection is no longer valid. "
                               "The user should reconnect from their Odoo "
                               "preferences."}

        if response.status_code >= 400:
            _logger.warning("xn_ai_graph: search returned %s: %s",
                            response.status_code, response.text[:300])
            return {"status": "error",
                    "message": "Document search is unavailable right now."}

        results = self._parse_hits(response.json())[:wanted]
        if not results:
            return {"status": "no_results",
                    "message": "No documents matched those terms. Only files "
                               "this user can already open are searched."}
        return {"status": "ok", "results": results}

    @api.model
    def _parse_hits(self, payload):
        """Turn Graph's response into a short list of actual documents.

        Two things are dropped here. Folders, because a driveItem hit is just
        as happily a directory, and a result reading "GST" with a link to a
        folder tells the reader nothing they can act on. And duplicates,
        because the same document backed up into two trees returns twice with
        identical names and the model then presents them as two findings.
        """
        results = []
        seen = set()
        for response_entry in payload.get('value') or []:
            for container in response_entry.get('hitsContainers') or []:
                for hit in container.get('hits') or []:
                    resource = hit.get('resource') or {}

                    # A file facet is what distinguishes a document from a
                    # folder. Folders carry a 'folder' facet instead.
                    if not resource.get('file'):
                        continue

                    name = resource.get('name')
                    link = resource.get('webUrl')
                    if not name or not link:
                        continue

                    key = name.lower()
                    if key in seen:
                        continue
                    seen.add(key)

                    results.append({
                        # The link is not decoration. An answer drawn from a
                        # document nobody can open to check is worse than no
                        # answer, because it cannot be challenged.
                        "title": name,
                        "link": link,
                        "location": self._location_of(resource),
                        "last_modified": (resource.get('lastModifiedDateTime')
                                          or '')[:10] or None,
                        "excerpt": self._clean_summary(hit.get('summary')),
                    })
        return results

    @api.model
    def _location_of(self, resource):
        """A short, human readable idea of where the file lives.

        The raw webUrl is a percent encoded path several folders deep and is
        unreadable in a chat reply. The immediate parent folder is usually
        enough for a reader to tell two similarly named files apart.
        """
        reference = resource.get('parentReference') or {}
        path = reference.get('path') or ''
        # Graph returns paths like "/drive/root:/Documents/Audits/2024"
        tail = path.split(':', 1)[-1].strip('/')
        if not tail:
            return None
        parts = [requests.utils.unquote(p) for p in tail.split('/') if p]
        return '/'.join(parts[-2:]) if parts else None
