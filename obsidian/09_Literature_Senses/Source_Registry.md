# Source_Registry.md

{
  "sources": [
    {
      "source_id": "arxiv",
      "live_status": "opt_in_only",
      "official_api": true,
      "requires_key": false,
      "default_mode": "fixture",
      "allowed_modes": [
        "fixture",
        "plan_only",
        "live_opt_in"
      ],
      "blocked_modes": [],
      "rate_limit_notes": "respect arXiv terms",
      "legal_notes": "metadata only",
      "citation_required": true,
      "full_text_allowed": false,
      "default_query_limit": 10,
      "max_query_limit": 50,
      "safety_notes": [
        "preprint_not_peer_reviewed",
        "overclaim_risk"
      ]
    },
    {
      "source_id": "pubmed",
      "live_status": "opt_in_only",
      "official_api": true,
      "requires_key": "optional",
      "default_mode": "fixture",
      "allowed_modes": [
        "fixture",
        "plan_only",
        "live_opt_in"
      ],
      "blocked_modes": [],
      "rate_limit_notes": "requires tool/email in live mode",
      "legal_notes": "abstract copyright constraints",
      "citation_required": true,
      "full_text_allowed": false,
      "default_query_limit": 10,
      "max_query_limit": 100,
      "safety_notes": [
        "clinical_overclaim"
      ]
    },
    {
      "source_id": "openalex",
      "live_status": "opt_in_only",
      "official_api": true,
      "requires_key": "optional",
      "default_mode": "fixture",
      "allowed_modes": [
        "fixture",
        "plan_only",
        "live_opt_in"
      ],
      "blocked_modes": [],
      "rate_limit_notes": "respect limits",
      "legal_notes": "metadata only",
      "citation_required": true,
      "full_text_allowed": false,
      "default_query_limit": 10,
      "max_query_limit": 100,
      "safety_notes": [
        "metadata_only"
      ]
    },
    {
      "source_id": "semantic_scholar",
      "live_status": "opt_in_only",
      "official_api": true,
      "requires_key": "optional",
      "default_mode": "fixture",
      "allowed_modes": [
        "fixture",
        "plan_only",
        "live_opt_in"
      ],
      "blocked_modes": [],
      "rate_limit_notes": "respect limits",
      "legal_notes": "metadata only",
      "citation_required": true,
      "full_text_allowed": false,
      "default_query_limit": 10,
      "max_query_limit": 100,
      "safety_notes": [
        "metadata_coverage_bias"
      ]
    },
    {
      "source_id": "local_fixture",
      "live_status": "disabled",
      "official_api": false,
      "requires_key": false,
      "default_mode": "fixture",
      "allowed_modes": [
        "fixture",
        "plan_only"
      ],
      "blocked_modes": [
        "live_opt_in"
      ],
      "rate_limit_notes": "none",
      "legal_notes": "synthetic fixtures",
      "citation_required": false,
      "full_text_allowed": true,
      "default_query_limit": 100,
      "max_query_limit": 1000,
      "safety_notes": []
    },
    {
      "source_id": "local_file",
      "live_status": "local_only",
      "official_api": false,
      "requires_key": false,
      "default_mode": "fixture",
      "allowed_modes": [
        "fixture",
        "plan_only"
      ],
      "blocked_modes": [
        "live_opt_in"
      ],
      "rate_limit_notes": "none",
      "legal_notes": "user-provided content only",
      "citation_required": true,
      "full_text_allowed": true,
      "default_query_limit": 100,
      "max_query_limit": 1000,
      "safety_notes": []
    }
  ]
}