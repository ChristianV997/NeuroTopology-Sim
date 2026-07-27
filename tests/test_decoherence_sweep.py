import json
import numpy as np
from physics.open_quantum import ThermalBathConfig,GapResult
from scripts.run_decoherence_sweep import make_parser,run_sweep

def test_temperature_detailed_balance():
 b=ThermalBathConfig.from_temperature(310,1e-3,thermal_relaxation_s=2e4,dephasing_rate_s=1e3,radiative_rate_s=1e2)
 assert np.isclose(b.thermal_excitation_s/b.thermal_relaxation_s,np.exp(-1e-3*1.602176634e-19/(1.380649e-23*310)))
def test_dense_sweep_artifacts(tmp_path):
 args=make_parser().parse_args(["--temperatures","10","310","--output-dir",str(tmp_path)])
 payload=run_sweep(args); assert [r["method"] for r in payload["records"]]==["exact_dense","exact_dense"]
 for name in ("decoherence_sweep.json","decoherence_sweep.csv","decoherence_sweep.png"): assert (tmp_path/name).is_file() and (tmp_path/name).stat().st_size>0
 loaded=json.loads((tmp_path/"decoherence_sweep.json").read_text()); assert loaded["schema"].endswith("v2")
 assert {"tau_subradiant_s","tau_superradiant_s","exhibits_chiral_current"}.issubset(loaded["records"][0])
def test_pumped_sweep_records_non_equilibrium_metadata(tmp_path):
 args=make_parser().parse_args(["--temperatures","310","--pump-rate","2e6","--pump-sites","0","4","--output-dir",str(tmp_path)])
 payload=run_sweep(args); record=payload["records"][0]
 assert record["metabolic_pump_rate_s"]==2e6 and record["pump_sites"]==[0,4]
def test_multilayer_selects_matrix_free(tmp_path):
 from unittest.mock import patch
 args=make_parser().parse_args(["--temperatures","310","--n-layers","2","--force-matrix-free","--output-dir",str(tmp_path)])
 fake=GapResult(1.0,1.0,0j,"matrix_free_estimate",0.0,0.0,0.0,1,False,True)
 with patch("scripts.run_decoherence_sweep.matrix_free_gap",return_value=fake): payload=run_sweep(args)
 assert payload["records"][0]["method"]=="matrix_free_estimate"
