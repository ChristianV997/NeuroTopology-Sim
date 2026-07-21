# Retrieval_Plan.md

{
  "retrieval_plan": [
    {
      "planned_query": "active_inference_allostasis",
      "source": "arxiv",
      "mode": "fixture",
      "live_command_template": "--live --confirm-network",
      "max_results": 10,
      "expected_fields": [
        "id",
        "title",
        "abstract"
      ],
      "rate_limit_notes": "respect arXiv terms",
      "legal_notes": "metadata only",
      "blocked_without_confirm_network": true,
      "requires_api_key": false,
      "output_target": "outputs/literature_senses/fixture_retrieved_papers.json"
    },
    {
      "planned_query": "active_inference_allostasis",
      "source": "pubmed",
      "mode": "fixture",
      "live_command_template": "--live --confirm-network",
      "max_results": 10,
      "expected_fields": [
        "id",
        "title",
        "abstract"
      ],
      "rate_limit_notes": "requires tool/email in live mode",
      "legal_notes": "abstract copyright constraints",
      "blocked_without_confirm_network": true,
      "requires_api_key": false,
      "output_target": "outputs/literature_senses/fixture_retrieved_papers.json"
    },
    {
      "planned_query": "active_inference_allostasis",
      "source": "openalex",
      "mode": "fixture",
      "live_command_template": "--live --confirm-network",
      "max_results": 10,
      "expected_fields": [
        "id",
        "title",
        "abstract"
      ],
      "rate_limit_notes": "respect limits",
      "legal_notes": "metadata only",
      "blocked_without_confirm_network": true,
      "requires_api_key": false,
      "output_target": "outputs/literature_senses/fixture_retrieved_papers.json"
    },
    {
      "planned_query": "active_inference_allostasis",
      "source": "semantic_scholar",
      "mode": "fixture",
      "live_command_template": "--live --confirm-network",
      "max_results": 10,
      "expected_fields": [
        "id",
        "title",
        "abstract"
      ],
      "rate_limit_notes": "respect limits",
      "legal_notes": "metadata only",
      "blocked_without_confirm_network": true,
      "requires_api_key": false,
      "output_target": "outputs/literature_senses/fixture_retrieved_papers.json"
    },
    {
      "planned_query": "active_inference_allostasis",
      "source": "local_fixture",
      "mode": "fixture",
      "live_command_template": "--live --confirm-network",
      "max_results": 100,
      "expected_fields": [
        "id",
        "title",
        "abstract"
      ],
      "rate_limit_notes": "none",
      "legal_notes": "synthetic fixtures",
      "blocked_without_confirm_network": true,
      "requires_api_key": false,
      "output_target": "outputs/literature_senses/fixture_retrieved_papers.json"
    },
    {
      "planned_query": "active_inference_allostasis",
      "source": "local_file",
      "mode": "fixture",
      "live_command_template": "--live --confirm-network",
      "max_results": 100,
      "expected_fields": [
        "id",
        "title",
        "abstract"
      ],
      "rate_limit_notes": "none",
      "legal_notes": "user-provided content only",
      "blocked_without_confirm_network": true,
      "requires_api_key": false,
      "output_target": "outputs/literature_senses/fixture_retrieved_papers.json"
    },
    {
      "planned_query": "computational_psychiatry",
      "source": "arxiv",
      "mode": "fixture",
      "live_command_template": "--live --confirm-network",
      "max_results": 10,
      "expected_fields": [
        "id",
        "title",
        "abstract"
      ],
      "rate_limit_notes": "respect arXiv terms",
      "legal_notes": "metadata only",
      "blocked_without_confirm_network": true,
      "requires_api_key": false,
      "output_target": "outputs/literature_senses/fixture_retrieved_papers.json"
    },
    {
      "planned_query": "computational_psychiatry",
      "source": "pubmed",
      "mode": "fixture",
      "live_command_template": "--live --confirm-network",
      "max_results": 10,
    