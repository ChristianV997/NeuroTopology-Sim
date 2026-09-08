from __future__ import annotations

from tools.research_report.compiler import compile_report

NOW = "2026-01-01T00:00:00+00:00"


def test_synthetic_dataset_never_reported_as_empirical(manifest_factory):
    manifest = manifest_factory(
        {
            "dataset_provenance": {
                "datasets": [
                    {"dataset_id": "synthetic_grid_32", "data_mode": "synthetic", "source": "generated", "license": None, "checksum": None, "n_subjects": None}
                ]
            },
            "falsification": {
                "results": [
                    {"hypothesis_id": "HYP-SYN-1", "data_mode": "synthetic", "metric_type": "proxy_K", "metric_value": 1.0, "unit": None, "verdict": "PASS", "notes": None}
                ]
            },
            "topology_validation": {
                "checks": [{"name": "synthetic_gate", "data_mode": "synthetic", "Qabs": 0.5, "I_mean": 0.2, "verdict": "PASS", "notes": None}]
            },
        }
    )

    report = compile_report(manifest, now=NOW)

    dataset = report["dataset_provenance"]["datasets"][0]
    assert dataset["data_mode"] == "synthetic"

    sve = report["synthetic_versus_empirical_distinction"]
    assert sve["datasets"]["synthetic"] == ["synthetic_grid_32"]
    assert sve["datasets"]["empirical"] == []
    assert sve["falsification_results"]["synthetic"] == ["HYP-SYN-1"]
    assert sve["falsification_results"]["empirical"] == []
    assert sve["topology_checks"]["synthetic"] == ["synthetic_gate"]
    assert sve["topology_checks"]["empirical"] == []

    limitations = " ".join(report["scientific_limitations"])
    assert "synthetic data and do not constitute empirical validation" in limitations
    assert "synthetic and are not a substitute for empirical replication" in limitations


def test_unrecognized_data_mode_is_unknown_not_a_guess(manifest_factory):
    manifest = manifest_factory(
        {
            "dataset_provenance": {
                "datasets": [{"dataset_id": "ambiguous_ds", "data_mode": "simulated", "source": None, "license": None, "checksum": None, "n_subjects": None}]
            }
        }
    )

    report = compile_report(manifest, now=NOW)
    dataset = report["dataset_provenance"]["datasets"][0]
    assert dataset["data_mode"] == "unknown"

    sve = report["synthetic_versus_empirical_distinction"]
    assert sve["datasets"]["unknown"] == ["ambiguous_ds"]
    assert sve["datasets"]["synthetic"] == []
    assert sve["datasets"]["empirical"] == []
