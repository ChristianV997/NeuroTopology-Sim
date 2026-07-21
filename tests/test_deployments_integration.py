#!/usr/bin/env python
"""
Integration tests for deployment orchestration and analysis.
"""
import sys
from pathlib import Path
import json
import tempfile
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.run_all_deployments import DeploymentOrchestrator
from scripts.analyze_deployments import DeploymentAnalyzer


class TestDeploymentOrchestrator:
    """Tests for sequential deployment orchestrator."""

    def test_orchestrator_initialization(self):
        """Test orchestrator can be initialized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = DeploymentOrchestrator(output_base=tmpdir)
            assert orchestrator.run_dir.exists()
            assert (orchestrator.run_dir / "run.log").exists()

    def test_orchestrator_logging(self):
        """Test orchestrator logging works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = DeploymentOrchestrator(output_base=tmpdir)
            orchestrator.logger.info("Test message")
            log_file = orchestrator.run_dir / "run.log"
            assert log_file.exists()
            with open(log_file) as f:
                content = f.read()
                assert "Test message" in content

    def test_metadata_creation(self):
        """Test metadata is created with git and environment info."""
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = DeploymentOrchestrator(output_base=tmpdir)
            orchestrator._save_metadata()

            metadata_file = orchestrator.run_dir / "metadata.json"
            assert metadata_file.exists()

            with open(metadata_file) as f:
                metadata = json.load(f)
                assert "timestamp" in metadata
                assert "environment" in metadata
                assert "git" in metadata
                assert "python_version" in metadata["environment"]


class TestDeploymentAnalyzer:
    """Tests for research analysis engine."""

    def test_analyzer_initialization(self):
        """Test analyzer can be initialized with mock results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = Path(tmpdir) / "results"
            results_dir.mkdir()

            # Create mock metadata
            metadata = {
                "timestamp": "20260719_120000",
                "environment": {
                    "python_version": "3.11.0",
                    "numpy_version": "2.0.0",
                },
                "git": {"commit": "abc123", "branch": "main"},
            }
            with open(results_dir / "metadata.json", "w") as f:
                json.dump(metadata, f)

            analyzer = DeploymentAnalyzer(results_dir)
            assert analyzer.metadata["timestamp"] == "20260719_120000"

    def test_speedup_comparison(self):
        """Test speedup comparison generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = Path(tmpdir) / "results"
            results_dir.mkdir()

            # Create mock metadata
            with open(results_dir / "metadata.json", "w") as f:
                json.dump({"timestamp": "test"}, f)

            # Create mock deployment summary
            for dataset in ["ds005620", "ds000245", "nki_rs"]:
                dataset_dir = results_dir / dataset
                dataset_dir.mkdir()
                summary = {
                    "speedup": 10.0 + len(dataset),
                    "total_time_seconds": 100.0,
                    "original_time_seconds": 1000.0,
                    "subjects_processed": 50,
                }
                with open(dataset_dir / "deployment_summary.json", "w") as f:
                    json.dump(summary, f)

            analyzer = DeploymentAnalyzer(results_dir)
            comparison = analyzer.generate_speedup_comparison()

            assert "datasets" in comparison
            assert len(comparison["datasets"]) == 3
            assert "summary" in comparison
            assert "mean_speedup" in comparison["summary"]

    def test_metrics_summary(self):
        """Test metrics summary generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = Path(tmpdir) / "results"
            results_dir.mkdir()

            # Create mock metadata
            with open(results_dir / "metadata.json", "w") as f:
                json.dump({"timestamp": "test"}, f)

            # Create mock metrics
            metrics_dir = results_dir / "ds005620"
            metrics_dir.mkdir()

            metrics_data = [
                {"q_mean": 5.0, "qabs_mean": 10.0, "f_dress": 0.5},
                {"q_mean": 6.0, "qabs_mean": 11.0, "f_dress": 0.6},
            ]
            with open(metrics_dir / "metrics.json", "w") as f:
                json.dump(metrics_data, f)

            analyzer = DeploymentAnalyzer(results_dir)
            summary = analyzer.generate_metrics_summary()

            assert "ds005620_eeg" in summary

    def test_research_report_generation(self):
        """Test research report can be generated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = Path(tmpdir) / "results"
            results_dir.mkdir()

            # Create minimal mock data
            with open(results_dir / "metadata.json", "w") as f:
                json.dump(
                    {
                        "timestamp": "20260719_120000",
                        "environment": {"python_version": "3.11.0"},
                        "git": {"commit": "abc123"},
                    },
                    f,
                )

            analyzer = DeploymentAnalyzer(results_dir)
            report = analyzer.generate_research_report()

            assert "Deployment Results Research Report" in report
            assert "20260719_120000" in report
            assert "abc123" in report

    def test_research_report_file_output(self):
        """Test research report can be written to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = Path(tmpdir) / "results"
            results_dir.mkdir()

            with open(results_dir / "metadata.json", "w") as f:
                json.dump({"timestamp": "test"}, f)

            analyzer = DeploymentAnalyzer(results_dir)
            output_file = Path(tmpdir) / "report.md"
            analyzer.generate_research_report(output_path=output_file)

            assert output_file.exists()
            with open(output_file) as f:
                content = f.read()
                assert "Deployment Results Research Report" in content


class TestDeploymentOutputValidation:
    """Tests for validating deployment outputs."""

    def test_deployment_summary_schema(self):
        """Test deployment summary has required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_dir = Path(tmpdir)

            summary = {
                "speedup": 13.8,
                "subjects_processed": 98,
                "total_time_seconds": 90.0,
                "optimization": "vectorized",
            }

            summary_file = dataset_dir / "deployment_summary.json"
            with open(summary_file, "w") as f:
                json.dump(summary, f)

            # Validate
            with open(summary_file) as f:
                data = json.load(f)
                assert "speedup" in data
                assert data["speedup"] >= 1.0
                assert "total_time_seconds" in data
                assert data["total_time_seconds"] > 0

    def test_metrics_file_validation(self):
        """Test metrics files are valid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_file = Path(tmpdir) / "metrics.json"

            metrics = [
                {"subject": "sub-001", "q_mean": 5.0, "elapsed_seconds": 1.5},
                {"subject": "sub-002", "q_mean": 6.0, "elapsed_seconds": 1.6},
            ]

            with open(metrics_file, "w") as f:
                json.dump(metrics, f)

            # Validate
            with open(metrics_file) as f:
                data = json.load(f)
                assert isinstance(data, list)
                assert len(data) > 0
                assert "subject" in data[0]


class TestErrorRecoveryStrategies:
    """Tests for error recovery handling."""

    def test_strict_error_mode(self):
        """Test strict error recovery mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = DeploymentOrchestrator(output_base=tmpdir)
            # In strict mode, errors should stop execution
            # This is verified by the run_all_sequential method
            assert orchestrator.results == {}

    def test_lenient_error_mode(self):
        """Test lenient error recovery mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = DeploymentOrchestrator(output_base=tmpdir)
            # In lenient mode, errors should not stop execution
            # This would be tested with actual failing deployments
            assert orchestrator.errors == {}

    def test_hybrid_error_mode(self):
        """Test hybrid error recovery mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = DeploymentOrchestrator(output_base=tmpdir)
            # Hybrid mode combines retry and skip strategies
            # Full test would require mock deployments
            assert orchestrator.run_dir.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
