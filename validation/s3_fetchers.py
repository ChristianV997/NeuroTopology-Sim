"""S3 fetchers for HCP-YA and NKI-RS fast-TR BOLD datasets.

This module provides production-ready S3 access for HCP-YA and NKI-RS, enabling
direct download of fast-TR BOLD data for phase-topology validation. Requires boto3
and AWS credentials (for HCP-YA) or no credentials (for NKI-RS, public bucket).

Usage:
------
# NKI-RS (no credentials needed, CC0 public)
from validation.s3_fetchers import NKIRSFetcher
fetcher = NKIRSFetcher(cache_dir="./nki_data")
bold_path = fetcher.fetch_subject("A00008326", session=1)
confounds_path = fetcher.fetch_confounds("A00008326", session=1)

# HCP-YA (requires ConnectomeDB login + AWS credentials)
from validation.s3_fetchers import HCPYAFetcher
fetcher = HCPYAFetcher(cache_dir="./hcp_data")
bold_path = fetcher.fetch_subject("100206", run=1)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
import warnings

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound
    BOTO_AVAILABLE = True
except ImportError:
    BOTO_AVAILABLE = False


class NKIRSFetcher:
    """Fetcher for NKI-RS (Nathan Kline Institute—Rockland Sample) dataset.

    NKI-RS is public (CC0), requires no credentials, and has TR=645ms.

    S3 bucket: nki-openaccess (no credentials needed)
    BIDS structure: sub-{id}/ses-{session}/func/sub-{id}_ses-{session}_task-rest_*.nii.gz
    """

    def __init__(
        self,
        cache_dir: str | Path = "~/nki_rs_data",
        profile: Optional[str] = None,
        region: str = "us-east-1",
    ):
        """Initialize NKI-RS fetcher.

        Parameters
        ----------
        cache_dir : str or Path
            Directory to cache downloaded files (default ~/nki_rs_data).
        profile : str, optional
            AWS profile name (not required for public bucket, but can speed up access).
        region : str
            AWS region for S3 access (default us-east-1).
        """
        if not BOTO_AVAILABLE:
            raise ImportError("boto3 required; pip install boto3")

        self.cache_dir = Path(cache_dir).expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.bucket = "nki-openaccess"
        self.region = region
        self.profile = profile

        # Create S3 client (public bucket, credentials optional)
        try:
            if profile:
                session = boto3.Session(profile_name=profile, region_name=region)
            else:
                session = boto3.Session(region_name=region)
            self.s3_client = session.client("s3", region_name=region)
            # Test connectivity
            self.s3_client.head_bucket(Bucket=self.bucket)
        except (NoCredentialsError, ClientError, ProfileNotFound) as exc:
            warnings.warn(
                f"Could not connect to NKI-RS S3 bucket: {exc}. "
                "NKI-RS is public (CC0), so no credentials are required.",
                RuntimeWarning,
            )

    def _s3_path(self, subject_id: str, session: int, dtype: str) -> str:
        """Build S3 path for a NKI-RS file.

        Parameters
        ----------
        subject_id : str
            Subject ID (e.g., "A00008326").
        session : int
            Session number.
        dtype : str
            Data type: "bold" or "confounds".

        Returns
        -------
        str
            S3 object key.
        """
        if dtype == "bold":
            return (
                f"sub-{subject_id}/ses-{session:02d}/func/"
                f"sub-{subject_id}_ses-{session:02d}_task-rest_bold.nii.gz"
            )
        elif dtype == "confounds":
            return (
                f"sub-{subject_id}/ses-{session:02d}/func/"
                f"sub-{subject_id}_ses-{session:02d}_task-rest_desc-preproc_physio.tsv"
            )
        else:
            raise ValueError(f"dtype must be 'bold' or 'confounds', got {dtype}")

    def fetch_subject(
        self,
        subject_id: str,
        session: int = 1,
        force: bool = False,
    ) -> str:
        """Fetch BOLD timeseries for one subject/session.

        Parameters
        ----------
        subject_id : str
            Subject ID (e.g., "A00008326").
        session : int
            Session number (default 1).
        force : bool
            Force re-download even if cached (default False).

        Returns
        -------
        str
            Path to cached BOLD file.

        Raises
        ------
        ClientError
            If S3 access fails.
        """
        local_path = (
            self.cache_dir
            / f"sub-{subject_id}_ses-{session:02d}_task-rest_bold.nii.gz"
        )

        if local_path.exists() and not force:
            return str(local_path)

        s3_key = self._s3_path(subject_id, session, "bold")
        try:
            self.s3_client.download_file(self.bucket, s3_key, str(local_path))
            return str(local_path)
        except ClientError as exc:
            raise RuntimeError(
                f"Failed to download {s3_key} from {self.bucket}: {exc}"
            ) from exc

    def fetch_confounds(
        self,
        subject_id: str,
        session: int = 1,
        force: bool = False,
    ) -> str:
        """Fetch confound regressors (physiology log) for one subject/session.

        Parameters
        ----------
        subject_id : str
            Subject ID.
        session : int
            Session number (default 1).
        force : bool
            Force re-download (default False).

        Returns
        -------
        str
            Path to cached confounds file.
        """
        local_path = (
            self.cache_dir
            / f"sub-{subject_id}_ses-{session:02d}_task-rest_desc-preproc_physio.tsv"
        )

        if local_path.exists() and not force:
            return str(local_path)

        s3_key = self._s3_path(subject_id, session, "confounds")
        try:
            self.s3_client.download_file(self.bucket, s3_key, str(local_path))
            return str(local_path)
        except ClientError as exc:
            warnings.warn(
                f"Could not download confounds {s3_key}: {exc}. "
                "Proceeding without confound regressors.",
                UserWarning,
            )
            return None

    def list_subjects(self, max_results: int = 100) -> list:
        """List available subjects in NKI-RS.

        Parameters
        ----------
        max_results : int
            Maximum number of results to return (default 100).

        Returns
        -------
        list
            List of subject IDs.
        """
        paginator = self.s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(
            Bucket=self.bucket,
            Prefix="sub-",
            Delimiter="/",
        )

        subjects = []
        for page in pages:
            for prefix in page.get("CommonPrefixes", []):
                subject_id = prefix["Prefix"].strip("sub-/")
                subjects.append(subject_id)
                if len(subjects) >= max_results:
                    return subjects
        return subjects


class HCPYAFetcher:
    """Fetcher for HCP-YA (Human Connectome Project Young Adult) dataset.

    HCP-YA requires ConnectomeDB registration (free DUA) and AWS credentials.
    TR=720ms, 1206 subjects.

    S3 bucket: hcp-openaccess (requires AWS credentials + ConnectomeDB auth)
    BIDS structure (preprocessed): HCP_1200/{subject}/MNINonLinear/Results/
    """

    def __init__(
        self,
        cache_dir: str | Path = "~/hcp_data",
        profile: Optional[str] = None,
        region: str = "us-east-1",
    ):
        """Initialize HCP-YA fetcher.

        Parameters
        ----------
        cache_dir : str or Path
            Directory to cache downloaded files (default ~/hcp_data).
        profile : str, optional
            AWS profile name (required for HCP-YA, from ConnectomeDB).
        region : str
            AWS region for S3 access (default us-east-1).

        Raises
        ------
        ImportError
            If boto3 is not installed.
        """
        if not BOTO_AVAILABLE:
            raise ImportError("boto3 required; pip install boto3")

        self.cache_dir = Path(cache_dir).expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.bucket = "hcp-openaccess"
        self.region = region
        self.profile = profile or "hcp"  # Default profile name for HCP

        # Create S3 client (requires valid credentials)
        try:
            session = boto3.Session(
                profile_name=self.profile, region_name=region
            )
            self.s3_client = session.client("s3", region_name=region)
            # Test connectivity
            self.s3_client.head_bucket(Bucket=self.bucket)
        except (NoCredentialsError, ClientError, ProfileNotFound) as exc:
            raise RuntimeError(
                f"Could not authenticate with HCP-YA bucket. "
                f"Ensure: (1) AWS credentials are configured for profile '{self.profile}', "
                f"(2) you have registered at ConnectomeDB "
                f"(https://db.humanconnectome.org/), and "
                f"(3) you have accepted the HCP Open Access DUA. "
                f"Error: {exc}"
            ) from exc

    def _s3_path(self, subject_id: str, run: int, dtype: str) -> str:
        """Build S3 path for an HCP-YA file.

        Parameters
        ----------
        subject_id : str
            HCP subject ID (e.g., "100206").
        run : int
            Run number (1-4).
        dtype : str
            Data type: "bold", "confounds", or "preproc".

        Returns
        -------
        str
            S3 object key.
        """
        if run not in (1, 2, 3, 4):
            raise ValueError(f"run must be 1-4, got {run}")

        prefix = f"HCP_1200/{subject_id}/MNINonLinear/Results/rfMRI_REST{run}_LR"

        if dtype == "bold":
            return f"{prefix}/rfMRI_REST{run}_LR.nii.gz"
        elif dtype == "confounds":
            return f"{prefix}/rfMRI_REST{run}_LR_Physio_log.txt"
        else:
            raise ValueError(f"dtype must be 'bold' or 'confounds', got {dtype}")

    def fetch_subject(
        self,
        subject_id: str,
        run: int = 1,
        force: bool = False,
    ) -> str:
        """Fetch BOLD timeseries for one subject/run.

        Parameters
        ----------
        subject_id : str
            HCP subject ID (e.g., "100206").
        run : int
            Run number (1-4, default 1).
        force : bool
            Force re-download even if cached (default False).

        Returns
        -------
        str
            Path to cached BOLD file.

        Raises
        ------
        ValueError
            If run is not 1-4.
        ClientError
            If S3 access fails.
        """
        if not (1 <= run <= 4):
            raise ValueError(f"run must be 1-4, got {run}")

        local_path = (
            self.cache_dir / f"sub-{subject_id}_ses-01_task-rest_run-{run}_bold.nii.gz"
        )

        if local_path.exists() and not force:
            return str(local_path)

        s3_key = self._s3_path(subject_id, run, "bold")
        try:
            self.s3_client.download_file(self.bucket, s3_key, str(local_path))
            return str(local_path)
        except ClientError as exc:
            raise RuntimeError(
                f"Failed to download {s3_key} from {self.bucket}: {exc}. "
                f"Ensure you have HCP ConnectomeDB credentials configured."
            ) from exc

    def fetch_confounds(
        self,
        subject_id: str,
        run: int = 1,
        force: bool = False,
    ) -> Optional[str]:
        """Fetch confound regressors (physiology log) for one subject/run.

        Parameters
        ----------
        subject_id : str
            HCP subject ID.
        run : int
            Run number (1-4, default 1).
        force : bool
            Force re-download (default False).

        Returns
        -------
        str or None
            Path to cached confounds file, or None if not available.
        """
        if not (1 <= run <= 4):
            raise ValueError(f"run must be 1-4, got {run}")

        local_path = (
            self.cache_dir / f"sub-{subject_id}_ses-01_task-rest_run-{run}_physio.txt"
        )

        if local_path.exists() and not force:
            return str(local_path)

        s3_key = self._s3_path(subject_id, run, "confounds")
        try:
            self.s3_client.download_file(self.bucket, s3_key, str(local_path))
            return str(local_path)
        except ClientError as exc:
            warnings.warn(
                f"Could not download confounds {s3_key}: {exc}. "
                "Proceeding without confound regressors.",
                UserWarning,
            )
            return None

    def list_subjects(self, max_results: int = 100) -> list:
        """List available subjects in HCP-YA.

        Parameters
        ----------
        max_results : int
            Maximum number of results to return (default 100).

        Returns
        -------
        list
            List of subject IDs.
        """
        paginator = self.s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(
            Bucket=self.bucket,
            Prefix="HCP_1200/",
            Delimiter="/",
        )

        subjects = []
        for page in pages:
            for prefix in page.get("CommonPrefixes", []):
                subject_id = prefix["Prefix"].replace("HCP_1200/", "").strip("/")
                if subject_id.isdigit():
                    subjects.append(subject_id)
                if len(subjects) >= max_results:
                    return subjects
        return subjects
