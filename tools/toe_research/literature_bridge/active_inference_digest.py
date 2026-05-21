import argparse
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();Path(a.out).write_text('''F = E_q[ln q(s) - ln p(o, s)]
ε_i = o_i - μ_i
weighted_prediction_error_i = Π_i ε_i
A = ∫ [c₁||x-x*||² + c₂||u||² + c₃||dμ/dt||²]dt
free-energy objective
precision weighting
allostatic cost
interoceptive/exteroceptive arbitration
recalibration latency
dukkha / taṇhā / upādāna
not proof''')
if __name__=='__main__':main()