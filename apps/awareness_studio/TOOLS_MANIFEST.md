# Awareness Studio — Tools Manifest

**Generated:** 2026-05-04  
**Session:** Claude Code (claude-sonnet-4-6) + activated MCP connectors  
**Branch:** feature/awareness-rag-phase2

---

## Discovery Method

Tools were enumerated by calling the MCP server list endpoints directly during the Claude Code session on 2026-05-04. All 5 connectors below responded successfully with live data.

---

## 1. MCP Connectors (Claude-session-only)

These connectors are accessible to Claude during an active session via the MCP protocol. They are **NOT callable from Python subprocesses** (e.g., `awareness-chat`, `awareness-web`). For Python-accessible equivalents, see Section 2.

| Connector | Provider | Tools | Read / Write | Auth Status |
|---|---|---|---|---|
| `mcp__26e1825a` | **Linear** | list_issues, list_projects, get_issue, save_issue, list_teams, list_users, list_milestones, save_milestone, list_documents, save_document, list_comments, save_comment, list_cycles, get_project, save_project, list_issue_labels, create_issue_label, create_attachment, delete_attachment, delete_comment, get_attachment, extract_images, get_issue_status, list_issue_statuses, list_project_labels, get_milestone, get_team, get_user, search_documentation | R+W | ✅ Working — team: DropshippingOS |
| `mcp__3bd5d21b` | **Netlify** | get-project, get-projects, get-forms-for-project (reader); create-project, deploy (updater) | R+W | ✅ Working — 2 projects found |
| `mcp__8c09d521` | **Supabase** | list_projects, execute_sql, apply_migration, create_branch, list_tables, generate_typescript_types, deploy_edge_function, get_logs, get_advisors, list_extensions, list_migrations, list_organizations | R+W | ✅ Working — no projects configured |
| `mcp__c6c573dd` | **Notion** | notion-search, notion-fetch, notion-create-pages, notion-create-database, notion-update-page, notion-query-database-view, notion-create-comment, notion-get-comments, notion-duplicate-page, notion-move-pages, notion-update-data-source, notion-create-view, notion-update-view, notion-query-meeting-notes, notion-get-teams, notion-get-users | R+W | ✅ Listed (not probed live) |
| `mcp__ed21a3d4` | **Google Drive** | search_files, read_file_content, download_file_content, get_file_metadata, get_file_permissions, list_recent_files, create_file, copy_file | R+W | ✅ Working — files found (owner: christian.villegard@gmail.com) |
| `mcp__57229d07` | **Auth** | authenticate, complete_authentication | R | ✅ Listed |
| `mcp__github` | **GitHub** | push_files, create_or_update_file, get_file_contents, list_commits, get_commit, create_branch, list_branches, list_pull_requests, pull_request_read, issue_read, issue_write, add_issue_comment, search_code, search_issues, search_repositories, merge_pull_request, create_pull_request, create_repository, get_me, and more | R+W | ✅ Working |

### Recommended Uses for Awareness Research (Claude-session tools)

**Linear** (via MCP):
- Pull roadmap items into answers ("what's next on the Awareness Studio roadmap?")
- Create evidence-tracking issues for each Evidence Card (`save_issue`)

**Netlify** (via MCP):
- Deploy the FastAPI app as a serverless function for demo access
- Manage staging vs production environments for web frontend

**Supabase** (via MCP):
- Store Evidence Log entries in a structured table (chunk_id, claim, EBT_confidence)
- Persist tool call logs for audit trail and DSPy training data

**Notion** (via MCP):
- Sync retrieved chunks back to the Notion knowledge base as comments
- Create new Notion pages from CANONICAL answer outputs

**Google Drive** (via MCP):
- Store generated book chapters as Drive documents
- Archive evaluation run outputs

**GitHub** (via MCP):
- Create PRs from this session; post review summaries

---

## 2. Python-Callable Routers (runtime, no MCP)

These are implemented in `tool_router.py` and callable from any Python process.

| Tool Name | Provider | Router Class | Auth Required | Rate Limit |
|---|---|---|---|---|
| `pubmed_search` | PubMed E-utilities | `LiteratureToolRouter` | No (key optional for higher rate limits) | 3 req/s (no key) / 10 req/s (with key) |
| `biorxiv_search` | bioRxiv API | `LiteratureToolRouter` | No | Public, generous |
| `linear_list_issues` | Linear GraphQL | `LinearToolRouter` | Yes (`LINEAR_API_KEY`) | 1,500 req/hour |

### Environment Variables

```bash
# Tool gating (default OFF)
TOOLS_ENABLED=false              # set to "true" to enable
TOOLS_ALLOWLIST=pubmed_search    # comma-separated; empty = allow all
TOOLS_MAX_CALLS_PER_REQUEST=1    # cap per web request or CLI invocation

# Optional API keys
PUBMED_API_KEY=your_key          # improves PubMed rate limits (free at NCBI)
LINEAR_API_KEY=lin_api_...       # enables /linear/search endpoint
```

---

## 3. Strict Allowlist (What the App Is Permitted to Call)

### READ-ONLY, always allowed (no key needed)
- `pubmed_search` — PubMed literature search
- `biorxiv_search` — bioRxiv/medRxiv preprint search

### READ-ONLY, requires API key
- `linear_list_issues` — Linear issue search (Linear GraphQL API)

### WRITE, never called automatically (requires explicit Claude-session action)
- All Notion write tools (`notion-create-pages`, `notion-update-page`, etc.)
- All Supabase write tools (`execute_sql`, `apply_migration`, etc.)
- All Netlify deploy tools
- All Google Drive write tools (`create_file`, `copy_file`)
- All GitHub write tools (`push_files`, `create_or_update_file`, `merge_pull_request`)
- `linear_save_issue` / `save_comment` (not exposed in Python router)

### NEVER called (blocked at router level)
- `authenticate`, `complete_authentication` — auth flow, never triggered by app
- Any tool not explicitly listed above

---

## 4. Plugin / Skills Assessment (Phase 3)

Claude Code in this environment does **not** expose an interactive plugin registry that Python code can extend. The available "skills" are the session-level skills loaded into the Claude Code harness (listed in system-reminder). No additional plugins were installed.

### Available Skills in This Session
| Skill | Purpose | Relevant to Awareness Studio |
|---|---|---|
| `claude-api` | Build/optimize Anthropic SDK apps | ✓ Can optimize llm_client.py for caching |
| `session-start-hook` | Repo startup hooks | ✓ Can ensure index is built on session start |
| `simplify` | Code quality review | ✓ Run on any changed file |
| `security-review` | Security audit | ✓ Review web endpoints |
| `init` | CLAUDE.md generation | ✓ Document the repo for future sessions |
| `fewer-permission-prompts` | Reduce tool approval noise | ✓ Allowlist read-only Bash commands |
| `review` | PR review | ✓ Auto-review PRs before merge |

### Gaps (Not Available)
- **Python Language Server / type hints**: Not available as a plugin. Use `pyright` or `mypy` via Bash directly.
- **Latest docs context plugin**: Not available. Use WebFetch for specific docs pages.
- **Dependency security scanning**: Not available as plugin. Run `pip-audit` via Bash.

---

## 5. Web Endpoints Summary (Phase 3 additions)

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/health` | GET | None | Liveness probe + tools_enabled flag |
| `/tools/list` | GET | None | List enabled tools in current config |
| `/chat` | POST | None | RAG chat with optional `use_tools` flag |
| `/literature/search` | POST | None | PubMed / bioRxiv search (always available) |
| `/linear/search` | GET | `LINEAR_API_KEY` | Read Linear issues |

---

## 6. Decision Log

| Decision | Rationale |
|---|---|
| MCP tools are session-only | Python processes can't call MCP servers directly; only Claude during active session |
| PubMed/bioRxiv use stdlib urllib | No extra dependencies; works in any Python 3.10+ env |
| `TOOLS_ENABLED=false` by default | Deterministic offline core must never make unexpected network calls |
| Linear read-only in Python | No write operations without explicit user action |
| Literature endpoint always available | `/literature/search` bypasses `TOOLS_ENABLED` since it's an explicit user request |
| Write MCP tools never auto-called | Epistemic hygiene: external data is [Hypothesis], never auto-pushed to sources |
