# Review: NotebookLM community MCP servers

- admission_status: experimental
- integration_mode: reference
- review_date: 2026-09-05

## Role
Unofficial MCP wrappers around NotebookLM web or Android backends.

## Evidence
Community servers such as PleasePrompto/notebooklm-mcp and ers123/notebooklm-mcp.
teng-lin/notebooklm-py states both backends rely on undocumented Google APIs.

## Constraints
Policy item 1: experimental unless based on an official supported API. Must not
be a required dependency. Cookies, master tokens, and Chromium automation are
forbidden in the repository and in tests.
