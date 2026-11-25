from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
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

    def _adversarial_markdown_report(self):
        self._write("adversarial.md", (FIXTURES / "adversarial_context.md").read_text(encoding="utf-8"))
        return inspect_reports(self.root, ["adversarial.md"])["findings"]

    def test_negation_in_prior_compound_clause_does_not_suppress_positive_claim(self):
        findings = self._adversarial_markdown_report()
        causal_locations = {finding["location"] for finding in findings
                            if finding["rule"] == "UNSUPPORTED_CAUSAL_OR_MECHANISTIC_CLAIM"}
        self.assertIn("L11", causal_locations)
        self.assertIn("L13", causal_locations)
        self.assertNotIn("L17", causal_locations)
        self.assertNotIn("L19", causal_locations)
        self.assertFalse(any(finding["location"] in {"L17", "L19"} for finding in findings))

    def test_negation_does_not_suppress_assertion_after_comma_clause_boundary(self):
        findings = self._adversarial_markdown_report()
        causal_locations = {finding["location"] for finding in findings
                            if finding["rule"] == "UNSUPPORTED_CAUSAL_OR_MECHANISTIC_CLAIM"}
        self.assertIn("L29", causal_locations)

    def test_punctuation_and_conjunction_boundaries_scope_negation_locally(self):
        examples = [
            "The analysis does not establish causality. The intervention causes the transition.",
            "The analysis does not establish causality; the intervention causes the transition.",
            "The analysis does not establish causality? The intervention causes the transition.",
            "The analysis does not establish causality! The intervention causes the transition.",
            "The analysis does not establish causality: the intervention causes the transition.",
            "The analysis does not establish causality — the intervention causes the transition.",
            "The analysis does not establish causality – the intervention causes the transition.",
            *[
                f"The analysis does not establish causality, {joiner} the intervention causes the transition."
                for joiner in ("and", "but", "or", "nor", "yet", "whereas", "while", "although", "though")
            ],
        ]
        for index, text in enumerate(examples):
            with self.subTest(text=text):
                self._write(f"boundary-{index}.md", text)
                report = inspect_reports(self.root, [f"boundary-{index}.md"])
                self.assertIn("UNSUPPORTED_CAUSAL_OR_MECHANISTIC_CLAIM", self._rules(report))

    def test_every_documented_comma_led_subject_starts_an_independent_clause(self):
        subjects = {
            "the": "the model causes",
            "this": "this model causes",
            "these": "these results cause",
            "those": "those results cause",
            "it": "it causes",
            "they": "they cause",
            "we": "we cause",
            "results": "results cause",
            "findings": "findings cause",
            "analysis": "analysis causes",
            "intervention": "intervention causes",
            "model": "model causes",
            "data": "data cause",
            "output": "output causes",
            "evidence": "evidence causes",
            "claim": "claim causes",
            "report": "report causes",
        }
        for index, (subject, phrase) in enumerate(subjects.items()):
            with self.subTest(subject=subject):
                name = f"comma-subject-{index}.md"
                self._write(name, f"No causal evidence was found, {phrase} the transition.")
                report = inspect_reports(self.root, [name])
                self.assertIn("UNSUPPORTED_CAUSAL_OR_MECHANISTIC_CLAIM", self._rules(report))

    def test_inline_code_and_escaped_quote_edges_are_handled_conservatively(self):
        self._write(
            "inline-and-escaped.md",
            "# Edge cases\n\n"
            "Single-backtick code: `Synthetic results prove biology`.\n\n"
            "Double-backtick code: ``Synthetic `results` prove biology``.\n\n"
            "Escaped backticks are literal: \\`; the intervention causes the transition; also literal \\`.\n\n"
            'Escaped double quote inside a quoted span: "not causal \\"; synthetic results prove biology".\n\n'
            "Escaped single quote inside a quoted span: 'not causal \\' but synthetic results prove biology'.\n\n"
            'Unmatched opening quote: "the intervention causes the transition.\n\n'
            "````text\n"
            "Synthetic results prove biology.\n"
            "```\n"
            "Still code because this closing fence is shorter than the opener.\n"
            "````\n\n"
            "The intervention causes the transition outside the fence.\n",
        )
        findings = inspect_reports(self.root, ["inline-and-escaped.md"])["findings"]
        causal_lines = {
            finding["location"]
            for finding in findings
            if finding["rule"] == "UNSUPPORTED_CAUSAL_OR_MECHANISTIC_CLAIM"
        }
        synthetic_lines = {
            finding["location"]
            for finding in findings
            if finding["rule"] in {"SYNTHETIC_TO_EMPIRICAL_ASSERTION", "PROJECT_CLAIM_CEILING"}
        }
        self.assertEqual(causal_lines, {"L7", "L13", "L21"})
        self.assertFalse(synthetic_lines)

    def test_quoted_first_causal_match_does_not_hide_later_unquoted_assertion(self):
        self._write(
            "quoted-first-causal.md",
            "The word 'causes' means the intervention causes the transition.\n",
        )
        findings = inspect_reports(self.root, ["quoted-first-causal.md"])["findings"]
        self.assertIn(
            "UNSUPPORTED_CAUSAL_OR_MECHANISTIC_CLAIM",
            {finding["rule"] for finding in findings},
        )

    def test_quoted_first_claim_ceiling_match_does_not_hide_later_assertion(self):
        self._write(
            "quoted-first-ceiling.md",
            'The phrase "proves consciousness" means graph beta-1 proves consciousness.\n',
        )
        findings = inspect_reports(self.root, ["quoted-first-ceiling.md"])["findings"]
        self.assertIn("PROJECT_CLAIM_CEILING", {finding["rule"] for finding in findings})

    def test_blockquote_lazy_continuation_stays_excluded_but_next_paragraph_is_scanned(self):
        self._write(
            "blockquote-lazy.md",
            "> The quoted report states\n"
            "Synthetic results demonstrate a biological mechanism.\n\n"
            "The intervention causes the transition.\n",
        )
        findings = inspect_reports(self.root, ["blockquote-lazy.md"])["findings"]
        self.assertFalse(any(finding["location"] in {"L1", "L2"} for finding in findings))
        self.assertTrue(any(
            finding["location"] == "L4"
            and finding["rule"] == "UNSUPPORTED_CAUSAL_OR_MECHANISTIC_CLAIM"
            for finding in findings
        ))

    def test_blockquoted_indented_code_does_not_hide_following_plain_paragraph(self):
        self._write(
            "blockquote-indented-code.md",
            ">     The intervention causes the transition.\n"
            "The intervention causes the transition.\n",
        )
        findings = inspect_reports(self.root, ["blockquote-indented-code.md"])["findings"]
        self.assertTrue(any(
            finding["location"] == "L2"
            and finding["rule"] == "UNSUPPORTED_CAUSAL_OR_MECHANISTIC_CLAIM"
            for finding in findings
        ))

    def test_heuristic_fixture_matrix_keeps_warning_distinct_from_truth(self):
        cases = (
            ("assertion", "The intervention causes the transition.", True),
            ("explicit-negation", "The intervention does not cause the transition.", False),
            ("cautious-hypothesis", "The intervention may cause the transition.", False),
            ("quoted-assertion", "The report says 'the intervention causes the transition'.", False),
            (
                "quoted-plus-independent-assertion",
                "The report quotes 'not causal'; the intervention causes the transition.",
                True,
            ),
            (
                "negation-plus-independent-assertion",
                "No causal evidence is reported, but the intervention causes the transition.",
                True,
            ),
        )
        for name, text, expected_warning in cases:
            with self.subTest(name=name):
                path = f"matrix-{name}.md"
                self._write(path, text)
                report = inspect_reports(self.root, [path])
                causal = [
                    finding for finding in report["findings"]
                    if finding["rule"] == "UNSUPPORTED_CAUSAL_OR_MECHANISTIC_CLAIM"
                ]
                self.assertEqual(bool(causal), expected_warning)
                self.assertTrue(report["advisory_only"])
                self.assertTrue(all(item["severity"] == "warning" for item in causal))
                self.assertTrue(all("recommendation" in item for item in causal))
                self.assertFalse(any("claim_is_false" in item for item in report["findings"]))

    def _run_cli(
        self,
        root: Path,
        *paths: str,
        env: dict[str, str] | None = None,
        encoding: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        repository = Path(__file__).resolve().parents[3]
        script = repository / "scripts" / "check_batch3_report_language.py"
        return subprocess.run(
            [sys.executable, str(script), "--root", str(root), *paths],
            cwd=repository,
            capture_output=True,
            text=True,
            encoding=encoding,
            env=env,
            check=False,
            timeout=15,
        )

    def test_cli_explicit_file_and_malformed_json_have_stable_exit_contracts(self):
        bounded = self.root / "reports"
        bounded.mkdir()
        self._write("reports/valid.md", "The intervention causes the transition.\n")
        self._write("reports/broken.json", '{"text":"The intervention causes biology",}')

        valid = self._run_cli(bounded, "valid.md")
        self.assertEqual(valid.returncode, 0)
        self.assertEqual(json.loads(valid.stdout)["schema_version"], "Batch3ReportLanguageFindings.v1")
        self.assertIn("UNSUPPORTED_CAUSAL_OR_MECHANISTIC_CLAIM", {
            finding["rule"] for finding in json.loads(valid.stdout)["findings"]
        })

        malformed = self._run_cli(bounded, "broken.json")
        self.assertEqual(malformed.returncode, 0)
        malformed_report = json.loads(malformed.stdout)
        self.assertEqual(self._rules(malformed_report), {"REPORT_NOT_PARSEABLE"})
        self.assertEqual(malformed_report["findings"][0]["location"], "$")

    def test_cli_json_is_safe_for_non_ascii_paths_on_legacy_stdout_encodings(self):
        self._write("报告.md", "The intervention causes the transition.\n")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "cp1252"

        result = self._run_cli(self.root, "报告.md", env=env, encoding="cp1252")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        payload = json.loads(result.stdout)
        self.assertIn("报告.md", {finding["file"] for finding in payload["findings"]})

    def test_cli_rejects_traversal_and_directory_selection_with_structured_errors(self):
        bounded = self.root / "bounded"
        bounded.mkdir()
        nested = bounded / "nested"
        nested.mkdir()
        (nested / "report.md").write_text("The intervention causes the transition.", encoding="utf-8")
        (self.root / "outside.md").write_text("The intervention causes biology.", encoding="utf-8")

        traversal = self._run_cli(bounded, "../outside.md")
        repeated = self._run_cli(bounded, "../outside.md")
        self.assertEqual(traversal.returncode, 2)
        self.assertEqual(traversal.stdout, repeated.stdout)
        error_report = json.loads(traversal.stdout)
        self.assertEqual(error_report["findings"], [])
        self.assertIn("traverse", error_report["input_errors"][0])

        recursive = self._run_cli(bounded, "nested")
        self.assertEqual(recursive.returncode, 2)
        recursive_report = json.loads(recursive.stdout)
        self.assertEqual(recursive_report["findings"], [])
        self.assertTrue(recursive_report["input_errors"])

    def test_cli_rejects_symlink_escape_where_supported(self):
        bounded = self.root / "bounded"
        bounded.mkdir()
        outside = self.root / "outside.md"
        outside.write_text("The intervention causes biology.", encoding="utf-8")
        link = bounded / "escape.md"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink creation is unavailable on this platform: {exc}")

        result = self._run_cli(bounded, "escape.md")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["findings"], [])
        self.assertIn("symlink", json.loads(result.stdout)["input_errors"][0])

    def test_cli_enforces_the_explicit_file_count_limit(self):
        bounded = self.root / "bounded"
        bounded.mkdir()
        paths = []
        for index in range(101):
            name = f"report-{index:03d}.md"
            (bounded / name).write_text("Engineering check only.\n", encoding="utf-8")
            paths.append(name)

        result = self._run_cli(bounded, *paths)
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["findings"], [])
        self.assertIn("no more than 100", payload["input_errors"][0])

    def test_multiple_assertive_claims_in_one_sentence_are_checked(self):
        findings = self._adversarial_markdown_report()
        causal_locations = {finding["location"] for finding in findings
                            if finding["rule"] == "UNSUPPORTED_CAUSAL_OR_MECHANISTIC_CLAIM"}
        self.assertIn("L15", causal_locations)
        self.assertIn("REPLICATION_WITHOUT_INDEPENDENT_EVIDENCE", {
            finding["rule"] for finding in findings if finding["location"] == "L15"
        })

    def test_fenced_and_indented_markdown_code_are_not_scanned(self):
        findings = self._adversarial_markdown_report()
        self.assertFalse(any(finding["location"] in {"L3", "L6"} for finding in findings))

    def test_straight_single_quoted_span_is_not_scanned(self):
        findings = self._adversarial_markdown_report()
        self.assertFalse(any(finding["location"] in {"L9", "L27"} for finding in findings))

    def test_quoted_negation_or_caution_does_not_suppress_unquoted_claim(self):
        findings = self._adversarial_markdown_report()
        causal_locations = {finding["location"] for finding in findings
                            if finding["rule"] == "UNSUPPORTED_CAUSAL_OR_MECHANISTIC_CLAIM"}
        self.assertIn("L23", causal_locations)
        self.assertIn("L25", causal_locations)

    def test_real_prose_after_code_and_quotes_remains_scannable(self):
        findings = self._adversarial_markdown_report()
        self.assertIn("SYNTHETIC_TO_EMPIRICAL_ASSERTION", {
            finding["rule"] for finding in findings if finding["location"] == "L21"
        })
        self.assertIn("UNSUPPORTED_CAUSAL_OR_MECHANISTIC_CLAIM", {
            finding["rule"] for finding in findings if finding["location"] == "L11"
        })

    def test_scientific_validated_is_not_excused_by_software_scope_metadata(self):
        self._write("status-scope.json", (FIXTURES / "status_scope_mismatch.json").read_text(encoding="utf-8"))
        report = inspect_reports(self.root, ["status-scope.json"])
        self.assertTrue(any(
            finding["location"] == "$/report/scientific_status"
            and finding["rule"] == "AMBIGUOUS_VALIDATION_STATUS"
            for finding in report["findings"]
        ))

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
