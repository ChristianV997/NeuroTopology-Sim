"""External-tool eligibility + adapter-contract checks for
`adapters.fmri_derivatives`.

Mirrors `adapters.mne_bids_contract` exactly (see that module's
docstring for the four fail-closed checks), targeting `nilearn` --
already a real, declared, `ready_for_adapter` dependency of this
repository (unlike `fmriprep`, which remains `external_cli`/`planned`;
see `external_tools/registry_seed.json`) -- as the tool this adapter's
`AdapterContractV1` is registered against.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from external_tools.adapter_contract import (
    AdapterContractRegistryError,
    AdapterContractV1,
    load_adapter_contracts,
)
from external_tools.registry import ExternalToolRegistry, RegistryError
from external_tools.tool_record import ExternalToolRecordV1

_REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TOOL_REGISTRY_PATH = _REPO_ROOT / "external_tools" / "registry_seed.json"
DEFAULT_ADAPTER_CONTRACTS_PATH = _REPO_ROOT / "external_tools" / "adapter_contracts_seed.json"
DEFAULT_TOOL_ID = "nilearn"
DEFAULT_ADAPTER_NAME = "fMRIPrep/Nilearn Derived fMRI Adapter v1"

_BLOCKED_TOOL_INTEGRATION_MODES: frozenset[str] = frozenset({"reference_only", "avoid_core"})
_BLOCKED_TOOL_LICENSE_RISK: frozenset[str] = frozenset({"agpl_high", "proprietary_high", "unknown_high"})


class AdapterEligibilityError(ValueError):
    """Raised when the adapter is not eligible to run against the current
    external-tool registry / adapter-contract state."""


@dataclass
class AdapterEligibility:
    tool: ExternalToolRecordV1
    contract: AdapterContractV1


def check_adapter_eligible(
    *,
    tool_id: str = DEFAULT_TOOL_ID,
    adapter_name: str = DEFAULT_ADAPTER_NAME,
    tool_registry_path: Optional[Path] = None,
    adapter_contracts_path: Optional[Path] = None,
) -> AdapterEligibility:
    """Fail closed unless the named tool is registered, not
    reference_only/avoid_core, not license-blocked, and has a valid,
    matching `AdapterContractV1`."""
    tool_registry_path = Path(tool_registry_path) if tool_registry_path else DEFAULT_TOOL_REGISTRY_PATH
    adapter_contracts_path = Path(adapter_contracts_path) if adapter_contracts_path else DEFAULT_ADAPTER_CONTRACTS_PATH

    try:
        tool_registry = ExternalToolRegistry.load(tool_registry_path)
    except RegistryError as exc:
        raise AdapterEligibilityError(f"external tool registry error: {exc}") from exc

    try:
        tool = tool_registry.get(tool_id)
    except RegistryError as exc:
        raise AdapterEligibilityError(f"external tool record '{tool_id}' not found: {exc}") from exc

    tool_errors = tool.validate()
    if tool_errors:
        raise AdapterEligibilityError(f"external tool record '{tool_id}' fails its own validation: {'; '.join(tool_errors)}")

    if tool.integration_mode in _BLOCKED_TOOL_INTEGRATION_MODES:
        raise AdapterEligibilityError(
            f"tool '{tool_id}' has integration_mode='{tool.integration_mode}', "
            "which is not eligible for adapter use"
        )
    if tool.license_risk in _BLOCKED_TOOL_LICENSE_RISK:
        raise AdapterEligibilityError(
            f"tool '{tool_id}' has license_risk='{tool.license_risk}', "
            "which is not eligible for adapter use"
        )
    if tool.commercial_use_status == "avoid_core":
        raise AdapterEligibilityError(f"tool '{tool_id}' has commercial_use_status='avoid_core'")

    try:
        contracts = load_adapter_contracts(adapter_contracts_path)
    except AdapterContractRegistryError as exc:
        raise AdapterEligibilityError(f"adapter contracts registry error: {exc}") from exc

    matching = [c for c in contracts.values() if c.tool_id == tool_id and c.adapter_name == adapter_name]
    if not matching:
        raise AdapterEligibilityError(
            f"no AdapterContractV1 found for tool_id='{tool_id}', adapter_name='{adapter_name}' "
            f"in {adapter_contracts_path}"
        )
    contract = matching[0]

    contract_errors = contract.validate()
    if contract_errors:
        raise AdapterEligibilityError(f"adapter contract '{contract.adapter_id}' fails its own validation: {'; '.join(contract_errors)}")

    if contract.integration_mode in _BLOCKED_TOOL_INTEGRATION_MODES:
        raise AdapterEligibilityError(f"adapter contract integration_mode='{contract.integration_mode}' is not eligible for use")

    return AdapterEligibility(tool=tool, contract=contract)
