from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

PR_TEMPLATE = ROOT / ".github" / "pull_request_template.md"
ONTOLOGY_CLAIM_REVIEW_ISSUE = ROOT / ".github" / "ISSUE_TEMPLATE" / "ontology_claim_review.yml"
PUBLICATION_READINESS_ISSUE = (
    ROOT / ".github" / "ISSUE_TEMPLATE" / "publication_readiness_review.yml"
)
ONTOLOGY_REVIEW_GOVERNANCE_DOC = ROOT / "docs" / "ontology_review_governance.md"
ONTOLOGY_CLAIM_REVIEW_CHECKLIST_DOC = ROOT / "docs" / "ontology_claim_review_checklist.md"


def test_new_ontology_governance_files_exist():
    assert ONTOLOGY_CLAIM_REVIEW_ISSUE.is_file()
    assert PUBLICATION_READINESS_ISSUE.is_file()
    assert ONTOLOGY_REVIEW_GOVERNANCE_DOC.is_file()
    assert ONTOLOGY_CLAIM_REVIEW_CHECKLIST_DOC.is_file()


def test_pr_template_contains_ontology_claim_scope_section():
    txt = PR_TEMPLATE.read_text(encoding="utf-8")
    assert "## Ontology / Claim Scope" in txt
    assert "- [ ] Marker-level claim: M" in txt
    assert "- [ ] Ontology-candidate claim: O" in txt
    assert "- [ ] Governance/evidence-state claim: Ω" in txt


def test_pr_template_contains_claim_promotion_requirements_section():
    txt = PR_TEMPLATE.read_text(encoding="utf-8")
    assert "## Claim Promotion Requirements" in txt
    assert "- [ ] Real execution artifacts exist before empirical claims" in txt
    assert "- [ ] C/Q/O claims remain quarantined unless independent evidence exists" in txt


def test_pr_template_contains_ontology_guardrails_section():
    txt = PR_TEMPLATE.read_text(encoding="utf-8")
    assert "## Ontology Guardrails" in txt
    assert "- [ ] No metric-to-ontology shortcut" in txt
    assert "- [ ] No empirical claim from mock E2E" in txt
    assert "- [ ] No O-layer claim promoted from EEG metrics alone" in txt


def test_ontology_claim_review_issue_template_contains_required_fields():
    txt = ONTOLOGY_CLAIM_REVIEW_ISSUE.read_text(encoding="utf-8")
    assert "label: claim title" in txt
    assert "label: proposed claim text" in txt
    assert "label: ontology layer" in txt
    assert "label: claim scope" in txt
    assert "label: dataset/run ID" in txt
    assert "label: evidence packet path" in txt
    assert "label: requested promotion state" in txt
    assert "label: reviewer decision" in txt


def test_ontology_claim_review_issue_template_contains_required_attestations():
    txt = ONTOLOGY_CLAIM_REVIEW_ISSUE.read_text(encoding="utf-8")
    assert "I am not claiming empirical support from mock E2E alone" in txt
    assert "I am not mapping EEG/topology metrics directly to ontology" in txt
    assert (
        "I am not treating sedation/unresponsiveness as direct experience labels" in txt
    )
    assert "I have listed alternative explanations" in txt
    assert "I have listed falsifiers" in txt
    assert "I have included required controls or marked claim as blocked" in txt


def test_publication_readiness_issue_template_contains_required_fields_and_checklist():
    txt = PUBLICATION_READINESS_ISSUE.read_text(encoding="utf-8")
    assert "label: package path" in txt
    assert "label: manuscript draft path" in txt
    assert "label: evidence packet path" in txt
    assert "label: artifact manifest path" in txt
    assert "label: claim promotion decision path" in txt
    assert "label: ontology evaluation path" in txt
    assert "label: requested publication status" in txt
    assert "Real execution completed, or package is clearly protocol-only" in txt
    assert "Validation summary passed" in txt
    assert "No banned overclaim language" in txt


def test_ontology_review_governance_doc_contains_required_sections_and_guardrails():
    txt = ONTOLOGY_REVIEW_GOVERNANCE_DOC.read_text(encoding="utf-8")
    assert "## 1. Purpose" in txt
    assert "## 5. D/M/T/C/Q/O/Ω layer definitions" in txt
    assert "## 8. Required evidence by claim type" in txt
    assert "## 12. Merge-blocking conditions" in txt
    assert "## 13. Publication-blocking conditions" in txt
    assert "Mock E2E supports engineering-runtime claims only." in txt
    assert "No metric-to-ontology shortcut." in txt
    assert "No O-layer claim promoted from EEG metrics alone." in txt


def test_ontology_claim_review_checklist_contains_decision_options():
    txt = ONTOLOGY_CLAIM_REVIEW_CHECKLIST_DOC.read_text(encoding="utf-8")
    assert "## Reviewer decision" in txt
    assert "approve_engineering_claim" in txt
    assert "approve_marker_candidate" in txt
    assert "approve_topology_candidate" in txt
    assert "block_pending_real_execution" in txt
    assert "block_pending_controls" in txt
    assert "block_pending_human_review" in txt
    assert "quarantine_C_Q_O_claim" in txt
    assert "reject_overreach" in txt
