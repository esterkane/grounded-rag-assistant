"""MCP layer for grounded-rag-assistant (Project 2).

Exposes Project 1's pure retrieval and generation functions as MCP tools.
``server.py`` registers three tools — ``retrieve_chunks``,
``answer_with_citations``, and ``list_documents`` — on the ``grounded-rag``
FastMCP server.
"""
