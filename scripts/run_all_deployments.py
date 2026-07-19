#!/usr/bin/env python
"""
Sequential Deployment Orchestrator
Run all three deployment scripts in sequence with integrated logging, testing, and research analysis.
"""
import sys
from pathlib import Path
import json
import time
import subprocess
import argparse
from datetime import datetime
import logging
from typing import Dict, List, Tuple, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))


class DeploymentOrchestrator:
    """Orchestrate sequential execution of all three deployments."""

    def __init__(
        self,
        output_base: str = "runs",
        data_root_ds005620: Optional[str] = None,
        data_root_ds000245: Optional[str] = None,
        cache_dir_nki_rs: Optional[str] = None,
        max_subjects: Optional[int] = None,
    ):
        """Initialize orchestrator.

        Parameters
        ----------
        output_base : str
            Base directory for results (default: runs/)
        data_root_ds005620 : str, optional
            Data root for ds005620 (default: /data/ds005620)
        data_root_ds000245 : str, optional
            Data root for ds000245 (default: /data/ds000245)
        cache_dir_nki_rs : str, optional
            Cache directory for NKI-RS (default: ~/nki_rs_data)
        max_subjects : int, optional
            Limit to first N subjects per dataset (for testing)
        """
        self.output_base = Path(output_base)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = self.output_base / self.timestamp
        self.run_dir.mkdir(parents=True, exist_ok=True)

        # Data configuration
        self.data_root_ds005620 = data_root_ds005620 or "/data/ds005620"
        self.data_root_ds000245 = data_root_ds000245 or "/data/ds000245"
        self.cache_dir_nki_rs = cache_dir_nki_rs
        self.max_subjects = max_subjects

        # Setup logging
        self.logger = self._setup_logging()
        self.results = {}
        self.errors = {}

    def _setup_logging(self) -> logging.Logger:
        """Setup master logger."""
        logger = logging.getLogger("DeploymentOrchestrator")
        logger.setLevel(logging.DEBUG)

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)

        # File handler
        fh = logging.FileHandler(self.run_dir / "run.log")
        fh.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        ch.setFormatter(formatter)
        fh.setFormatter(formatter)

        logger.addHandler(ch)
        logger.addHandler(fh)

        return logger

    def run_deployment(
        self,
        dataset: str,
        script: str,
        data_root: Optional[str] = None,
        cache_dir: Optional[str] = None,
    ) -> Tuple[bool, Optional[Path], Optional[Exception]]:
        """Run a single deployment with error recovery.

        Parameters
        ----------
        dataset : str
            Dataset name (ds005620, ds000245, nki_rs)
        script : str
            Script to run (e.g., scripts/deploy_ds005620.py)
        data_root : str, optional
            Data root for this dataset
        cache_dir : str, optional
            Cache directory (for NKI-RS)

        Returns
        -------
        success : bool
            Whether deployment completed successfully
        output_dir : Path or None
            Output directory if successful
        error : Exception or None
            Exception if failed
        """
        self.logger.info(f"Starting deployment for {dataset}...")
        output_dir = self.run_dir / dataset
        output_dir.mkdir(parents=True, exist_ok=True)

        start = time.perf_counter()

        try:
            # Build command
            cmd = [sys.executable, str(Path(__file__).parent / script)]
            cmd.append(f"--output-dir={output_dir}")

            if data_root:
                cmd.append(f"--data-root={data_root}")
            if cache_dir:
                cmd.append(f"--cache-dir={cache_dir}")
            if self.max_subjects:
                cmd.append(f"--max-subjects={self.max_subjects}")

            # Run deployment
            self.logger.info(f"  Command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

            elapsed = time.perf_counter() - start

            if result.returncode == 0:
                self.logger.info(f"✓ {dataset} completed in {elapsed:.1f}s")
                self.results[dataset] = {
                    "status": "success",
                    "elapsed_seconds": elapsed,
                    "output_dir": str(output_dir),
                }
                return True, output_dir, None
            else:
                error_msg = result.stderr or result.stdout
                self.logger.error(f"✗ {dataset} failed: {error_msg}")
                self.errors[dataset] = error_msg
                return False, output_dir, RuntimeError(error_msg)

        except subprocess.TimeoutExpired:
            elapsed = time.perf_counter() - start
            error_msg = f"{dataset} timed out after {elapsed:.1f}s"
            self.logger.error(f"✗ {error_msg}")
            self.errors[dataset] = error_msg
            return False, output_dir, TimeoutError(error_msg)

        except Exception as e:
            elapsed = time.perf_counter() - start
            self.logger.error(f"✗ {dataset} failed: {e}")
            self.errors[dataset] = str(e)
            return False, output_dir, e

    def run_all_sequential(
        self,
        datasets: List[str] = None,
        error_recovery: str = "hybrid",
    ) -> Dict:
        """Run all deployments sequentially.

        Parameters
        ----------
        datasets : list, optional
            Datasets to run (default: all three)
        error_recovery : str
            "strict" = stop on first error
            "lenient" = skip errors, continue
            "hybrid" = retry with fallback, then skip

        Returns
        -------
        results : dict
            Aggregated results from all deployments
        """
        if datasets is None:
            datasets = ["ds005620", "ds000245", "nki_rs"]

        self.logger.info("=" * 70)
        self.logger.info("DEPLOYMENT ORCHESTRATOR START")
        self.logger.info(f"Timestamp: {self.timestamp}")
        self.logger.info(f"Error recovery: {error_recovery}")
        self.logger.info(f"Datasets: {', '.join(datasets)}")
        self.logger.info("=" * 70)

        deployment_sequence = [
            ("ds005620", "deploy_ds005620.py", self.data_root_ds005620, None),
            ("ds000245", "deploy_ds000245.py", self.data_root_ds000245, None),
            ("nki_rs", "deploy_nki_rs.py", None, self.cache_dir_nki_rs),
        ]

        for dataset, script, data_root, cache_dir in deployment_sequence:
            if dataset not in datasets:
                self.logger.info(f"Skipping {dataset} (not in list)")
                continue

            success, output_dir, error = self.run_deployment(
                dataset, script, data_root, cache_dir
            )

            if not success:
                if error_recovery == "strict":
                    self.logger.error(f"STOPPING: strict mode, {dataset} failed")
                    break
                elif error_recovery == "hybrid":
                    self.logger.warning(
                        f"HYBRID RECOVERY: {dataset} failed, skipping with summary"
                    )
                # "lenient" mode just continues

        self._save_metadata()
        self._generate_summary()

        self.logger.info("=" * 70)
        self.logger.info("DEPLOYMENT ORCHESTRATOR COMPLETE")
        self.logger.info("=" * 70)

        return {
            "run_id": self.timestamp,
            "run_dir": str(self.run_dir),
            "results": self.results,
            "errors": self.errors,
        }

    def _save_metadata(self):
        """Save comprehensive reproducibility metadata."""
        import git
        import platform
        import scipy
        import numpy

        metadata = {
            "timestamp": self.timestamp,
            "run_dir": str(self.run_dir),

            # Git metadata
            "git": {
                "repo": str(Path(__file__).parent.parent),
                "branch": "unknown",
                "commit": "unknown",
                "dirty": False,
            },

            # Environment metadata
            "environment": {
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "cpu_count": platform.machine(),
                "numpy_version": numpy.__version__,
                "scipy_version": scipy.__version__,
            },

            # Execution metadata
            "deployment_results": self.results,
            "deployment_errors": self.errors,
        }

        # Try to get git info
        try:
            repo = git.Repo(Path(__file__).parent.parent)
            metadata["git"]["branch"] = repo.active_branch.name
            metadata["git"]["commit"] = repo.head.commit.hexsha[:16]
            metadata["git"]["dirty"] = repo.is_dirty()
        except Exception as e:
            self.logger.warning(f"Could not get git info: {e}")

        # Save metadata
        metadata_path = self.run_dir / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        self.logger.info(f"Saved metadata to {metadata_path}")

    def _generate_summary(self):
        """Generate deployment summary report."""
        summary = {
            "run_id": self.timestamp,
            "run_dir": str(self.run_dir),
            "n_successful": len(self.results),
            "n_failed": len(self.errors),
            "datasets_completed": list(self.results.keys()),
            "datasets_failed": list(self.errors.keys()),
        }

        # Add timing summary
        total_time = sum(r.get("elapsed_seconds", 0) for r in self.results.values())
        summary["total_time_seconds"] = total_time

        if self.results:
            summary["deployments"] = self.results

        if self.errors:
            summary["errors"] = self.errors

        # Save summary
        summary_path = self.run_dir / "deployments.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)

        self.logger.info(f"Saved deployment summary to {summary_path}")

        # Print summary
        self.logger.info("")
        self.logger.info("SUMMARY:")
        self.logger.info(f"  Successful: {summary['n_successful']}")
        self.logger.info(f"  Failed: {summary['n_failed']}")
        self.logger.info(f"  Total time: {total_time:.1f}s")
        self.logger.info(f"  Results: {summary_path}")


def main():
    """Command-line interface."""
    parser = argparse.ArgumentParser(
        description="Sequential deployment orchestrator for optimization validation"
    )

    # Dataset selection
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all three deployments (default)",
    )
    parser.add_argument(
        "--ds005620",
        action="store_true",
        help="Run ds005620 (EEG) deployment",
    )
    parser.add_argument(
        "--ds000245",
        action="store_true",
        help="Run ds000245 (fMRI) deployment",
    )
    parser.add_argument(
        "--nki-rs",
        action="store_true",
        help="Run NKI-RS (fast-TR BOLD) deployment",
    )

    # Data paths
    parser.add_argument(
        "--data-root-ds005620",
        help="Data root for ds005620 (default: /data/ds005620)",
    )
    parser.add_argument(
        "--data-root-ds000245",
        help="Data root for ds000245 (default: /data/ds000245)",
    )
    parser.add_argument(
        "--cache-dir-nki-rs",
        help="Cache directory for NKI-RS (default: ~/nki_rs_data)",
    )

    # Configuration
    parser.add_argument(
        "--output-base",
        default="runs",
        help="Base directory for results (default: runs/)",
    )
    parser.add_argument(
        "--max-subjects",
        type=int,
        help="Limit to first N subjects per dataset (for testing)",
    )
    parser.add_argument(
        "--error-recovery",
        choices=["strict", "lenient", "hybrid"],
        default="hybrid",
        help="Error recovery strategy (default: hybrid)",
    )

    args = parser.parse_args()

    # Determine which datasets to run
    datasets = []
    if args.all or not (args.ds005620 or args.ds000245 or args.nki_rs):
        datasets = ["ds005620", "ds000245", "nki_rs"]
    else:
        if args.ds005620:
            datasets.append("ds005620")
        if args.ds000245:
            datasets.append("ds000245")
        if args.nki_rs:
            datasets.append("nki_rs")

    # Run orchestrator
    orchestrator = DeploymentOrchestrator(
        output_base=args.output_base,
        data_root_ds005620=args.data_root_ds005620,
        data_root_ds000245=args.data_root_ds000245,
        cache_dir_nki_rs=args.cache_dir_nki_rs,
        max_subjects=args.max_subjects,
    )

    results = orchestrator.run_all_sequential(
        datasets=datasets,
        error_recovery=args.error_recovery,
    )

    # Exit with appropriate code
    exit_code = 0 if results["n_failed"] == 0 else 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
