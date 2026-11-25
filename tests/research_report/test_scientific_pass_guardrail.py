from __future__ import annotations

from tools.research_report.compiler import compile_report
from tools.research_report.render_markdown import render_markdown

NOW = "2026-01-01T00:00:00+00:00"


def test_proxy_k_pass_is_never_labeled_a_formal_bayes_factor(manifest_factory):
    manifest = manifest_factory(
        {
            "falsification": {
                "results": [
                    {
                        "hypothesis_id": "HYP-PROXY-1",
                        "data_mode": "synthetic",
                        "metric_type": "proxy_K",
                        "metric_value": 4.7,
                        "unit": None,
                        "verdict": "PASS",
                        "notes": "Proxy statistic only; not a validated Bayes factor.",
                    }
                ]
            }
        }
    )

    report = compile_report(manifest, now=NOW)

    result = report["falsification_status"]["results"][0]
    assert result["verdict"] == "PASS"
    assert result["metric_type"] == "proxy_K"
    assert result["is_formal_bayes_factor"] is False
    assert result["display_label"] == "proxy_K (not a formal Bayes factor)"

    limitations = " ".join(report["scientific_limitations"])
    assert "not formal Bayes factors" in limitations

    markdown = render_markdown(report)
    # Isolate the Falsification Status table (the limitations section below
    # it discusses proxy metrics in prose, with its own, differently-worded
    # caveat -- this checks the actual result row, not free text).
    section = markdown.split("## Falsification Status")[1].split("## Synthetic")[0]
    proxy_lines = [line for line in section.splitlines() if "proxy_K" in line]
    assert proxy_lines
    assert all("(not a formal Bayes factor)" in line for line in proxy_lines if "Bayes factor" in line)


def test_declared_bayes_factor_is_labeled_as_such(manifest_factory):
    manifest = manifest_factory(
        {
            "falsification": {
                "results": [
                    {
                        "hypothesis_id": "HYP-BF-1",
                        "data_mode": "empirical",
                        "metric_type": "bayes_factor",
                        "metric_value": 12.0,
                        "unit": None,
                        "verdict": "PASS",
                        "notes": None,
                    }
                ]
            }
        }
    )

    report = compile_report(manifest, now=NOW)
    result = report["falsification_status"]["results"][0]
    assert result["is_formal_bayes_factor"] is True
    assert result["display_label"] == "Bayes factor"
