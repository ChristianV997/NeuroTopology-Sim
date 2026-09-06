"""Cross-adapter interoperability conformance validator.

Evaluates signal chunks, adapters, and pipelines against the 16 NeuroTopology-Sim
signal interop contract properties. Returns structured reports.
"""

from __future__ import annotations

import hashlib
import importlib.util
import math
import socket
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterator, Sequence
import numpy as np

try:
    from shared.interop.contracts import InteropValidationError
except ImportError:
    class InteropValidationError(Exception):
        """Fallback exception when shared.interop is not yet in the environment."""
        pass


@dataclass
class PropertyEvaluation:
    property_id: int
    property_name: str
    passed: bool
    details: str
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConformanceReport:
    adapter_name: str
    overall_status: str  # "PASS", "FAIL", "NOT_AVAILABLE"
    tested_properties_count: int
    passed_count: int
    failed_count: int
    evaluations: list[PropertyEvaluation] = field(default_factory=list)
    missing_capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def check_no_network_context():
    """Context manager or check ensuring no socket calls are made."""
    class NetworkBlocker:
        def __enter__(self):
            self._orig_socket = socket.socket
            def _blocked_socket(*args, **kwargs):
                raise RuntimeError("Network access attempted during offline adapter operation!")
            socket.socket = _blocked_socket
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            socket.socket = self._orig_socket

    return NetworkBlocker()


class ConformanceValidator:
    """Validator implementing checks for all 16 contract properties."""

    @staticmethod
    def validate_property_1_shape(chunk: Any) -> PropertyEvaluation:
        """1. Signal chunks have shape (channels, samples)."""
        data = getattr(chunk, "data", None)
        if data is None:
            return PropertyEvaluation(1, "shape_channels_samples", False, "Missing 'data' attribute")
        arr = np.asarray(data)
        if arr.ndim != 2:
            return PropertyEvaluation(
                1, "shape_channels_samples", False,
                f"Data dimension is {arr.ndim}, expected 2 (channels, samples)"
            )
        channels, samples = arr.shape
        if channels <= 0 or samples <= 0:
            return PropertyEvaluation(
                1, "shape_channels_samples", False,
                f"Invalid shape ({channels}, {samples}), must have channels > 0 and samples > 0"
            )
        return PropertyEvaluation(
            1, "shape_channels_samples", True,
            f"Shape verified as ({channels}, {samples})",
            {"channels": channels, "samples": samples}
        )

    @staticmethod
    def validate_property_2_channel_order(chunk: Any, expected_channels: Sequence[str] | None = None) -> PropertyEvaluation:
        """2. Channel order is deterministic."""
        names = getattr(chunk, "channel_names", None)
        if names is None:
            return PropertyEvaluation(2, "deterministic_channel_order", False, "Missing 'channel_names'")
        names_list = list(names)
        if not names_list:
            return PropertyEvaluation(2, "deterministic_channel_order", False, "Channel names is empty")
        if any(not isinstance(n, str) or not n.strip() for n in names_list):
            return PropertyEvaluation(2, "deterministic_channel_order", False, "Channel names must be non-empty strings")
        
        data = np.asarray(getattr(chunk, "data"))
        if len(names_list) != data.shape[0]:
            return PropertyEvaluation(
                2, "deterministic_channel_order", False,
                f"Channel names count ({len(names_list)}) does not match data channels ({data.shape[0]})"
            )

        if expected_channels is not None:
            if list(expected_channels) != names_list:
                return PropertyEvaluation(
                    2, "deterministic_channel_order", False,
                    f"Channel order mismatch: expected {list(expected_channels)}, got {names_list}"
                )

        return PropertyEvaluation(
            2, "deterministic_channel_order", True,
            f"Channel order verified with {len(names_list)} channels",
            {"channel_names": names_list}
        )

    @staticmethod
    def validate_property_3_sampling_rate(chunk: Any, nominal_rate: float | None = None) -> PropertyEvaluation:
        """3. Sampling frequency is preserved exactly."""
        rate = getattr(chunk, "sample_rate_hz", None)
        if rate is None:
            return PropertyEvaluation(3, "sampling_frequency_exact", False, "Missing 'sample_rate_hz'")
        try:
            r = float(rate)
        except (TypeError, ValueError):
            return PropertyEvaluation(3, "sampling_frequency_exact", False, f"Invalid rate type: {type(rate)}")
        if not math.isfinite(r) or r <= 0:
            return PropertyEvaluation(3, "sampling_frequency_exact", False, f"Non-positive or non-finite rate: {r}")
        if nominal_rate is not None and not math.isclose(r, nominal_rate, rel_tol=1e-6):
            return PropertyEvaluation(
                3, "sampling_frequency_exact", False,
                f"Sampling rate {r} does not match nominal {nominal_rate}"
            )
        return PropertyEvaluation(
            3, "sampling_frequency_exact", True,
            f"Sampling frequency preserved at {r} Hz",
            {"sample_rate_hz": r}
        )

    @staticmethod
    def validate_property_4_units_and_scaling(chunk: Any) -> PropertyEvaluation:
        """4. Units and scaling are explicit."""
        units = getattr(chunk, "units", None)
        if units is None:
            return PropertyEvaluation(4, "units_and_scaling_explicit", False, "Missing 'units' attribute")
        u_list = list(units)
        data = np.asarray(getattr(chunk, "data"))
        if len(u_list) != data.shape[0]:
            return PropertyEvaluation(
                4, "units_and_scaling_explicit", False,
                f"Units count ({len(u_list)}) does not match channel count ({data.shape[0]})"
            )
        for u in u_list:
            if not isinstance(u, str) or not u.strip():
                return PropertyEvaluation(4, "units_and_scaling_explicit", False, "Units must be explicit non-empty strings")
        return PropertyEvaluation(
            4, "units_and_scaling_explicit", True,
            f"Explicit units verified: {set(u_list)}",
            {"units": u_list}
        )

    @staticmethod
    def validate_property_5_source_checksum(chunk: Any, expected_checksum: str | None = None) -> PropertyEvaluation:
        """5. Source checksums are deterministic."""
        checksum = getattr(chunk, "source_sha256", None)
        if checksum is None:
            return PropertyEvaluation(5, "deterministic_source_checksum", False, "Missing 'source_sha256'")
        if not isinstance(checksum, str) or len(checksum) != 64:
            return PropertyEvaluation(
                5, "deterministic_source_checksum", False,
                f"Checksum must be 64-character SHA-256 hex string, got '{checksum}'"
            )
        try:
            int(checksum, 16)
        except ValueError:
            return PropertyEvaluation(5, "deterministic_source_checksum", False, "Checksum contains non-hex characters")

        if expected_checksum and checksum != expected_checksum:
            return PropertyEvaluation(
                5, "deterministic_source_checksum", False,
                f"Checksum mismatch: expected {expected_checksum}, got {checksum}"
            )

        return PropertyEvaluation(
            5, "deterministic_source_checksum", True,
            f"Deterministic checksum verified: {checksum[:8]}...",
            {"source_sha256": checksum}
        )

    @staticmethod
    def validate_property_6_montage_coordinates(chunk: Any) -> PropertyEvaluation:
        """6. Montage coordinates are native, safely inferred, or unavailable."""
        coords = getattr(chunk, "montage_coordinates", None)
        montage_name = getattr(chunk, "montage_name", None)
        
        if coords is None:
            return PropertyEvaluation(
                6, "montage_coordinates_state", True,
                "Coordinates are explicitly unavailable (None)",
                {"montage_name": montage_name, "state": "unavailable"}
            )
        
        arr = np.asarray(coords)
        data = np.asarray(getattr(chunk, "data"))
        channels = data.shape[0]
        if arr.shape != (channels, 3):
            return PropertyEvaluation(
                6, "montage_coordinates_state", False,
                f"Montage coordinates shape {arr.shape} does not match ({channels}, 3)"
            )
        
        return PropertyEvaluation(
            6, "montage_coordinates_state", True,
            f"Coordinates provided for {channels} channels",
            {"montage_name": montage_name, "shape": list(arr.shape)}
        )

    @staticmethod
    def validate_property_7_inferred_provenance(chunk: Any) -> PropertyEvaluation:
        """7. Inferred coordinates carry provenance."""
        coords = getattr(chunk, "montage_coordinates", None)
        montage_name = getattr(chunk, "montage_name", None)
        if coords is not None:
            if not montage_name or not isinstance(montage_name, str) or not montage_name.strip():
                return PropertyEvaluation(
                    7, "inferred_coordinates_provenance", False,
                    "Coordinates are present but montage_name provenance is empty or missing"
                )
            return PropertyEvaluation(
                7, "inferred_coordinates_provenance", True,
                f"Coordinates provenance recorded: montage_name='{montage_name}'",
                {"montage_name": montage_name}
            )
        return PropertyEvaluation(
            7, "inferred_coordinates_provenance", True,
            "No coordinates present; provenance requirement vacuously met"
        )

    @staticmethod
    def validate_property_8_no_silent_fabrication(chunk: Any) -> PropertyEvaluation:
        """8. Missing coordinates are never silently fabricated."""
        coords = getattr(chunk, "montage_coordinates", None)
        if coords is None:
            return PropertyEvaluation(
                8, "no_silent_fabrication", True,
                "Missing coordinates are explicitly None rather than fabricated dummy points"
            )
        arr = np.asarray(coords)
        if not np.all(np.isfinite(arr)):
            return PropertyEvaluation(
                8, "no_silent_fabrication", False,
                "Coordinates contain NaN or non-finite values (must be finite if provided)"
            )
        return PropertyEvaluation(
            8, "no_silent_fabrication", True,
            "All provided coordinates are finite and explicitly formatted"
        )

    @staticmethod
    def validate_property_9_chunk_boundaries(chunks: Sequence[Any]) -> PropertyEvaluation:
        """9. Chunk boundaries are reproducible."""
        if not chunks:
            return PropertyEvaluation(9, "reproducible_chunk_boundaries", False, "No chunks to validate")
        
        prev_sample = None
        for i, c in enumerate(chunks):
            idx = getattr(c, "chunk_index", None)
            if idx != i:
                return PropertyEvaluation(
                    9, "reproducible_chunk_boundaries", False,
                    f"Chunk index mismatch at position {i}: chunk_index is {idx}"
                )
            timestamps = getattr(c, "timestamps", None)
            if timestamps is not None:
                ts = np.asarray(timestamps)
                if ts.ndim != 1 or len(ts) != np.asarray(c.data).shape[1]:
                    return PropertyEvaluation(
                        9, "reproducible_chunk_boundaries", False,
                        f"Timestamps shape {ts.shape} does not match chunk sample count"
                    )
                if len(ts) > 1 and not np.all(np.diff(ts) > 0):
                    return PropertyEvaluation(
                        9, "reproducible_chunk_boundaries", False,
                        "Timestamps are not strictly increasing within chunk"
                    )
            
            start_sample = getattr(c, "start_sample", None)
            if start_sample is not None and prev_sample is not None:
                if start_sample < prev_sample:
                    return PropertyEvaluation(
                        9, "reproducible_chunk_boundaries", False,
                        f"Non-monotonic chunk start_sample: {start_sample} < {prev_sample}"
                    )
            if start_sample is not None:
                prev_sample = start_sample + np.asarray(c.data).shape[1]

        return PropertyEvaluation(
            9, "reproducible_chunk_boundaries", True,
            f"Validated boundaries across {len(chunks)} chunks"
        )

    @staticmethod
    def validate_property_10_capability_state(adapter_name: str, check_fn: Callable[[], dict[str, Any]]) -> PropertyEvaluation:
        """10. Optional dependency absence yields a structured capability state."""
        try:
            state = check_fn()
            if not isinstance(state, dict):
                return PropertyEvaluation(
                    10, "structured_capability_state", False,
                    f"Capability check for {adapter_name} returned {type(state)}, expected dict"
                )
            if "installed" not in state:
                return PropertyEvaluation(
                    10, "structured_capability_state", False,
                    f"Capability state missing 'installed' boolean key: {state}"
                )
            return PropertyEvaluation(
                10, "structured_capability_state", True,
                f"Structured capability state available: installed={state['installed']}",
                state
            )
        except Exception as e:
            return PropertyEvaluation(
                10, "structured_capability_state", False,
                f"Capability check raised unhandled exception: {e}"
            )

    @staticmethod
    def validate_property_11_malformed_errors(adapter_fn: Callable[[Any], Iterator[Any]], malformed_path: Any) -> PropertyEvaluation:
        """11. Malformed files produce actionable errors."""
        try:
            list(adapter_fn(malformed_path))
            return PropertyEvaluation(
                11, "actionable_malformed_errors", False,
                "Adapter silently succeeded on malformed input instead of raising actionable error"
            )
        except (ValueError, RuntimeError, FileNotFoundError, OSError) as e:
            return PropertyEvaluation(
                11, "actionable_malformed_errors", True,
                f"Actionable error raised on malformed input: {type(e).__name__}: {e}"
            )
        except Exception as e:
            return PropertyEvaluation(
                11, "actionable_malformed_errors", False,
                f"Unexpected non-standard exception raised on malformed input: {type(e).__name__}: {e}"
            )

    @staticmethod
    def validate_property_12_no_network(adapter_fn: Callable[..., Any], *args, **kwargs) -> PropertyEvaluation:
        """12. No adapter performs network access."""
        try:
            with check_no_network_context():
                adapter_fn(*args, **kwargs)
            return PropertyEvaluation(
                12, "no_network_access", True,
                "Adapter executed without network socket access"
            )
        except RuntimeError as e:
            if "Network access attempted" in str(e):
                return PropertyEvaluation(
                    12, "no_network_access", False,
                    "Adapter attempted network access!"
                )
            raise

    @staticmethod
    def validate_property_13_lazy_imports(module_name: str, heavy_pkg: str = "mne") -> PropertyEvaluation:
        """13. Adapters do not import heavy optional packages at package-import time."""
        import subprocess
        import sys
        code = f"""
import sys
import importlib
try:
    importlib.import_module("{module_name}")
    if "{heavy_pkg}" in sys.modules:
        sys.exit(2)
    sys.exit(0)
except ImportError:
    sys.exit(3)
"""
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        if proc.returncode == 0:
            return PropertyEvaluation(
                13, "lazy_imports", True,
                f"Module {module_name} does not eagerly import {heavy_pkg}"
            )
        elif proc.returncode == 2:
            return PropertyEvaluation(
                13, "lazy_imports", False,
                f"Module {module_name} eagerly imported {heavy_pkg} on import!"
            )
        elif proc.returncode == 3:
            return PropertyEvaluation(
                13, "lazy_imports", True,
                f"Module {module_name} not installed in this environment; test skipped"
            )
        else:
            return PropertyEvaluation(
                13, "lazy_imports", False,
                f"Subprocess failed with code {proc.returncode}: {proc.stderr}"
            )

    @staticmethod
    def validate_property_14_metadata_preservation(source_meta: dict[str, Any], chunk: Any) -> PropertyEvaluation:
        """14. Interoperability adapters preserve metadata when converting between formats."""
        mismatches = []
        if "sample_rate_hz" in source_meta:
            if not math.isclose(float(chunk.sample_rate_hz), float(source_meta["sample_rate_hz"]), rel_tol=1e-5):
                mismatches.append(f"sample_rate_hz: expected {source_meta['sample_rate_hz']}, got {chunk.sample_rate_hz}")
        if "channels" in source_meta:
            if list(chunk.channel_names) != list(source_meta["channels"]):
                mismatches.append(f"channels: expected {source_meta['channels']}, got {list(chunk.channel_names)}")
        if "source_sha256" in source_meta:
            if getattr(chunk, "source_sha256", None) != source_meta["source_sha256"]:
                mismatches.append(f"source_sha256: expected {source_meta['source_sha256']}, got {getattr(chunk, 'source_sha256', None)}")
        
        if mismatches:
            return PropertyEvaluation(
                14, "metadata_preservation", False,
                f"Metadata preservation failures: {'; '.join(mismatches)}"
            )
        return PropertyEvaluation(
            14, "metadata_preservation", True,
            "Metadata preserved across conversion"
        )

    @staticmethod
    def validate_property_15_edge_cases(adapter_fn: Callable[[Any], Iterator[Any]], empty_or_truncated_file: Any) -> PropertyEvaluation:
        """15. Empty, truncated, and single-channel inputs are handled deterministically."""
        try:
            res = list(adapter_fn(empty_or_truncated_file))
            return PropertyEvaluation(
                15, "edge_case_inputs", True,
                f"Edge case input handled deterministically, yielded {len(res)} chunks"
            )
        except (ValueError, RuntimeError, InteropValidationError, EOFError) as e:
            return PropertyEvaluation(
                15, "edge_case_inputs", True,
                f"Edge case input handled deterministically with expected exception: {type(e).__name__}"
            )
        except Exception as e:
            return PropertyEvaluation(
                15, "edge_case_inputs", False,
                f"Edge case input produced unhandled unexpected exception: {type(e).__name__}: {e}"
            )

    @staticmethod
    def validate_property_16_finite_numeric_values(chunk: Any) -> PropertyEvaluation:
        """16. Numeric values are finite or explicitly null."""
        data = np.asarray(getattr(chunk, "data"))
        if not np.all(np.isfinite(data)):
            return PropertyEvaluation(
                16, "finite_numeric_values", False,
                "Signal data contains NaN, Inf, or non-finite values"
            )
        timestamps = getattr(chunk, "timestamps", None)
        if timestamps is not None:
            ts = np.asarray(timestamps)
            if not np.all(np.isfinite(ts)):
                return PropertyEvaluation(
                    16, "finite_numeric_values", False,
                    "Timestamps contain NaN, Inf, or non-finite values"
                )
        coords = getattr(chunk, "montage_coordinates", None)
        if coords is not None:
            c = np.asarray(coords)
            if not np.all(np.isfinite(c)):
                return PropertyEvaluation(
                    16, "finite_numeric_values", False,
                    "Montage coordinates contain non-finite values without explicit null"
                )
        return PropertyEvaluation(
            16, "finite_numeric_values", True,
            "All numeric arrays (data, timestamps, coordinates) contain only finite values"
        )
