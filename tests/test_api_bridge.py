import json
import numpy as np
from sim.pitnn.api_bridge import (export_falsification_payload, export_liouvillian_ep_payload,
    export_rg_magnetization_payload, export_topology_trace_payload)
from scripts.export_dsim_artifacts import export_artifacts

def test_payload_schemas_and_dimensions():
    field = np.arange(4 * 6 * 3, dtype=float).reshape(4, 6, 3)
    rg = export_rg_magnetization_payload(field, np.arange(4, dtype=float), downsample_factor=2)
    assert rg["frame_count"] == 2 and len(rg["heatmap_sz"]) == 6
    trace = export_topology_trace_payload([{"time_s": 0, "winding_number": 1, "topological_charge": .2, "beta1_loops": 2}])
    assert trace["beta1_loops"] == [2]
    ep = export_liouvillian_ep_payload({"pump_values": [0, 1], "loss_values": [0, 1], "gaps": [[1, 2], [3, 4]]})
    assert ep["grid_shape"] == [2, 2]
    verdict = export_falsification_payload({"bayes_factor": 1.0, "verdict": "NOT_SUPPORTED", "comparison": {"pitnn": {"rss": 1, "aicc": 2}, "classical_wilson_cowan": {"rss": 3, "aicc": 4}}})
    assert verdict["verdict"] == "NOT_SUPPORTED"

def test_export_orchestrator_writes_offline_bundle(tmp_path):
    npz = tmp_path / "field.npz"
    np.savez_compressed(npz, magnetization=np.ones((5, 4, 3)), timestamps_s=np.arange(5, dtype=float))
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"ep_boundary": {"pump_s": 1.5, "loss_s": 2.5, "global_gap": .01, "fidelity": .9, "liouvillian_gap_proxy": .01}, "bayes_factor": 1.0, "verdict": "NOT_SUPPORTED", "comparison": {"pitnn": {"rss": 1, "aicc": 2}, "classical_wilson_cowan": {"rss": 2, "aicc": 3}}}))
    manifest = export_artifacts(summary, npz, tmp_path / "export", downsample_factor=2)
    assert manifest["offline"] is True
    assert (tmp_path / "export" / "dsim_manifest.json").is_file()
    assert (tmp_path / "export" / "rg_magnetization_frames.npz").is_file()
    assert json.loads((tmp_path / "export" / "falsification_summary.json").read_text())["verdict"] == "NOT_SUPPORTED"
