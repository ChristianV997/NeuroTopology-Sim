from __future__ import annotations

import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.batch3_report_firewall.checker import InputSelectionError, inspect_reports

FIXTURES = Path(__file__).parent / "fixtures"


class ReportFirewallTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write(self, name: str, content: str | bytes) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path

    @staticmethod
    def _rules(report: dict) -> set[str]:
        return {finding["rule"] for finding in report["findings"]}

    def test_markdown_assertions_flagged_but_negations_quotes_and_caution_are_not(self):
        self._write("report.md", (FIXTURES / "assertions.md").read_text(encoding="utf-8"))
        report = inspect_reports(self.root, ["report.md"])
        rules = self._rules(report)
        self.assertTrue(
            {
                "SYNTHETIC_TO_EMPIRICAL_ASSERTION",
                "ENGINEERING_TO_BIOLOGICAL_VALIDATION",
                "UNSUPPORTED_CAUSAL_OR_MECHANISTIC_CLAIM",
                "REPLICATION_WITHOUT_INDEPENDENT_EVIDENCE",
                "AMBIGUOUS_VALIDATION_STATUS",
                "MISSING_EVIDENCE_REFERENCE",
            }.issubset(rules)
        )
        self.assertTrue(all(f["severity"] == "warning" for f in report["findings"]))
        self.assertTrue(all("recommendation" in f and "location" in f and "file" in f for f in report["findings"]))
        self.assertFalse(any(
            f["location"] == "L10" and f["rule"] == "SYNTHETIC_TO_EMPIRICAL_ASSERTION"
            for f in report["findings"]
        ))
        excluded_lines = {"L6", "L26", "L30", "L31", "L32", "L36", "L38", "L54", "L58"}
        self.assertFalse(any(f["location"] in excluded_lines for f in report["findings"]))

    def test_structured_status_mismatch_and_mixed_sections(self):
        self._write("report.json", (FIXTURES / "status_mismatch.json").read_text(encoding="utf-8"))
        report = inspect_reports(self.root, ["report.json"])
        rules = self._rules(report)
        self.assertTrue(
            {"STRUCTURED_EVIDENCE_STATUS_MISMATCH", "SCIENTIFIC_PASS_FIELD_TRUE", "AMBIGUOUS_VALIDATION_STATUS"}.issubset(rules)
        )
        self.assertFalse(any(
            f["location"] == "$/sections[0]/text" and f["rule"] == "STRUCTURED_EVIDENCE_STATUS_MISMATCH"
            for f in report["findings"]
        ))
        self.assertFalse(any(f["location"] == "$/fixture_metadata/text" for f in report["findings"]))
        self.assertFalse(any(
            f["location"] == "$/sections[1]" and f["rule"] == "MISSING_EVIDENCE_REFERENCE"
            for f in report["findings"]
        ))

    def test_nested_empirical_claim_conflicts_with_inherited_synthetic_mode(self):
        self._write(
            "inherited.json",
            json.dumps({"data_mode": "synthetic", "claim": {"claim_category": "empirical_observation", "text": "The outcome is measurable."}}),
        )
        report = inspect_reports(self.root, ["inherited.json"])
        self.assertTrue(any(
            f["location"] == "$/claim" and f["rule"] == "STRUCTURED_EVIDENCE_STATUS_MISMATCH"
            for f in report["findings"]
        ))

    def test_mixed_markdown_sections_do_not_cross_contaminate(self):
        self._write(
            "mixed.md",
            "# Mixed report\n\n## Synthetic results\n\nSynthetic fixture output is not empirical evidence.\n\n"
            "## Empirical observations\n\nDescriptive empirical observations are linked to "
            "[EVIDENCE-9](https://example.invalid/evidence/9).\n",
        )
        self.assertEqual(inspect_reports(self.root, ["mixed.md"])["findings"], [])

    def test_project_claim_ceiling_is_reused_and_engineering_limitation_is_exempt(self):
        self._write(
            "ceiling.md",
            "# Report\n\nThe graph beta-1 proves consciousness.\n\n"
            "Software conformance does not validate biological function.\n\n"
            "```text\nSynthetic results confirm biology.\n```\n",
        )
        report = inspect_reports(self.root, ["ceiling.md"])
        rules = self._rules(report)
        self.assertIn("PROJECT_CLAIM_CEILING", rules)
        self.assertNotIn("ENGINEERING_TO_BIOLOGICAL_VALIDATION", rules)
        self.assertNotIn("SYNTHETIC_TO_EMPIRICAL_ASSERTION", rules)

    def test_synthetic_results_labeled_as_real_data_are_flagged(self):
        self._write("real_data.md", "Synthetic fixture results are presented as real data.\n")
        self.assertIn("SYNTHETIC_TO_EMPIRICAL_ASSERTION", self._rules(inspect_reports(self.root, ["real_data.md"])))

    def test_replication_with_independent_reference_is_not_flagged(self):
        self._write(
            "replication.md",
            "# Report\n\nThe finding was replicated in an independent cohort "
            "[EVIDENCE-2](https://example.invalid/evidence/2).\n",
        )
        report = inspect_reports(self.root, ["replication.md"])
        self.assertNotIn("REPLICATION_WITHOUT_INDEPENDENT_EVIDENCE", self._rules(report))
        self.assertNotIn("MISSING_EVIDENCE_REFERENCE", self._rules(report))

    def test_json_scientific_claim_without_reference_is_flagged(self):
        self._write(
            "claim.json",
            json.dumps({"claim": {"claim_category": "empirical_observation", "text": "The intervention causes the transition."}}),
        )
        report = inspect_reports(self.root, ["claim.json"])
        self.assertIn("UNSUPPORTED_CAUSAL_OR_MECHANISTIC_CLAIM", self._rules(report))
        self.assertIn("MISSING_EVIDENCE_REFERENCE", self._rules(report))

    def test_json_explicit_limitation_is_not_reported_as_a_missing_empirical_reference(self):
        self._write(
            "limitation.json",
            json.dumps({"evidence_class": "empirical_observation", "text": "The output is not biological validation."}),
        )
        report = inspect_reports(self.root, ["limitation.json"])
        self.assertNotIn("MISSING_EVIDENCE_REFERENCE", self._rules(report))

    def test_json_limitation_section_is_not_scanned_as_an_assertion(self):
        self._write(
            "limitations.json",
            json.dumps({"limitations": {"text": "Synthetic results prove biology."}}),
        )
        self.assertEqual(inspect_reports(self.root, ["limitations.json"])["findings"], [])

    def test_explicit_json_fixture_field_is_not_treated_as_a_report_claim(self):
        self._write("fixture.json", json.dumps({"fixture": {"text": "Synthetic results prove biology."}}))
        self.assertEqual(inspect_reports(self.root, ["fixture.json"])["findings"], [])

    def test_output_is_deterministic_and_does_not_emit_a_scientific_status(self):
        self._write("a.md", "Status: VALIDATED\n")
        self._write("b.json", '{"scientific_pass": true}')
        first = inspect_reports(self.root, ["b.json", "a.md"])
        second = inspect_reports(self.root, ["a.md", "b.json"])
        self.assertEqual(first, second)
        self.assertEqual(set(first), {"schema_version", "advisory_only", "review_recommended", "findings"})
        self.assertNotIn("status", first)

    def test_software_pass_is_not_promoted_or_mislabeled(self):
        self._write(
            "engineering.json",
            json.dumps({"status": "PASS", "validation_scope": "software", "evidence_class": "engineering_fact", "scientific_pass": False}),
        )
        report = inspect_reports(self.root, ["engineering.json"])
        self.assertEqual(report["findings"], [])
        self.assertNotIn("status", report)

    def test_paths_are_explicit_relative_and_bounded(self):
        bounded = self.root / "bounded"
        bounded.mkdir()
        outside = self.root / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        for selected in ("../outside.json", str(outside), "."):
            with self.subTest(selected=selected), self.assertRaises(InputSelectionError):
                inspect_reports(bounded, [selected])

    def test_symlink_escape_is_rejected(self):
        bounded = self.root / "bounded"
        bounded.mkdir()
        outside = self.root / "outside-report.json"
        outside.write_text("{}", encoding="utf-8")
        link = bounded / "escape.json"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            # Exercise the same rejection branch where Windows symlink creation
            # is unavailable to the current user, without changing privileges.
            link.write_text("{}", encoding="utf-8")
            with patch.object(Path, "is_symlink", autospec=True, side_effect=lambda path: path == link):
                with self.assertRaises(InputSelectionError):
                    inspect_reports(bounded, ["escape.json"])
            return
        with self.assertRaises(InputSelectionError):
            inspect_reports(bounded, ["escape.json"])

    def test_only_markdown_and_json_are_accepted_and_size_is_bounded(self):
        self._write("report.txt", "text")
        with self.assertRaises(InputSelectionError):
            inspect_reports(self.root, ["report.txt"])
        self._write("large.json", b" " * 2_000_001)
        with self.assertRaises(InputSelectionError):
            inspect_reports(self.root, ["large.json"])

    def test_inspected_content_is_never_executed_and_no_network_is_used(self):
        marker = self.root / "should-not-exist"
        malicious = f"__import__('pathlib').Path({str(marker)!r}).write_text('executed')"
        self._write("untrusted.json", json.dumps({"text": malicious}))

        def blocked(*_args, **_kwargs):
            raise AssertionError("network access attempted")

        with patch.object(socket, "create_connection", blocked), patch.object(socket.socket, "connect", blocked):
            inspect_reports(self.root, ["untrusted.json"])
        self.assertFalse(marker.exists())

    def test_malformed_json_is_reported_without_free_text_scanning(self):
        self._write("broken.json", '{"text": "the intervention causes biology",}')
        report = inspect_reports(self.root, ["broken.json"])
        self.assertEqual(self._rules(report), {"REPORT_NOT_PARSEABLE"})
        self.assertEqual(report["findings"][0]["location"], "$")

    def test_duplicate_json_keys_are_not_silently_accepted(self):
        self._write("duplicate.json", '{"scientific_pass": false, "scientific_pass": true}')
        report = inspect_reports(self.root, ["duplicate.json"])
        self.assertEqual(self._rules(report), {"REPORT_NOT_PARSEABLE"})

    def test_excessively_deep_json_is_bounded(self):
        payload = {"text": "content"}
        for _ in range(70):
            payload = {"nested": payload}
        self._write("deep.json", json.dumps(payload))
        report = inspect_reports(self.root, ["deep.json"])
        self.assertIn("REPORT_STRUCTURE_TOO_DEEP", self._rules(report))


if __name__ == "__main__":
    unittest.main()
