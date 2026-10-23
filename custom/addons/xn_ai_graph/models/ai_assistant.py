# -*- coding: utf-8 -*-
from odoo import models, api, _
import logging

_logger = logging.getLogger(__name__)


class AiAssistant(models.AbstractModel):
    """Adds document search to the assistant when this module is installed.

    The dependency runs this way round on purpose: xn_ai_graph extends the
    assistant, rather than the assistant depending on Graph. Uninstalling
    this module removes the tool and leaves a working HR assistant behind.
    """

    _inherit = 'ai.assistant'

    @api.model
    def _tool_schemas(self):
        schemas = super()._tool_schemas()
        schemas.append({
            "type": "function",
            "function": {
                "name": "search_documents",
                "description": (
                    "Search the current user's Microsoft SharePoint and "
                    "OneDrive documents. Use for questions about policies, "
                    "handbooks, templates and other company documents. "
                    "Returns only files this user can already open."),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "Search terms, as you would type into a "
                                "search box. Keep it short: two or three "
                                "keywords find more than a sentence."),
                        },
                    },
                    "required": ["query"],
                },
            },
        })
        schemas.append({
            "type": "function",
            "function": {
                "name": "read_document",
                "description": (
                    "Read the contents of one document found by "
                    "search_documents, to answer a question about what it "
                    "actually says. Use this rather than guessing from a "
                    "document's title."),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "document_id": {
                            "type": "string",
                            "description": (
                                "The document_id returned by "
                                "search_documents. Not a URL."),
                        },
                        "about": {
                            "type": "string",
                            "description": (
                                "What you are looking for in the document, "
                                "in a few words. Long documents are narrowed "
                                "to the passages nearest these terms, so "
                                "being specific finds more than being broad."),
                        },
                    },
                    "required": ["document_id"],
                },
            },
        })
        return schemas

    @api.model
    def tool_search_documents(self, query=None):
        if not query or not query.strip():
            return {"error": "No search terms were given."}
        return self.env['xn.graph.search'].search_documents(query.strip())

    @api.model
    def tool_read_document(self, document_id=None, about=None):
        if not document_id:
            return {"error": "No document was given to read."}
        return self.env['xn.graph.document'].read_document(
            document_id, about=about)
