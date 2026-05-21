import argparse
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();Path(a.out).write_text('''Q = (1 / 2π) Σ_p wrap(Δφ_p)
Qabs = (1 / 2π) Σ_p |wrap(Δφ_p)|
fdress = (Qabs - |Q|) / (|Q| + ε)
persistent Hodge Laplacian
persistent local Laplacian
sheaf consistency error
directed Hodge flow
causal topology
local-global mismatch
topology transition distance
E_sheaf(x) = Σ_(v,e) ||ρ_{v←e}(x_e) - x_v||²
L_sheaf = δᵀδ
Guardrail: Q/Qabs/fdress are candidate topology telemetry only.''')
if __name__=='__main__':main()