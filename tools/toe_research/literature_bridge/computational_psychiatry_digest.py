import argparse
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();Path(a.out).write_text('''latent parameters
attractor dwell
recovery latency
exit cost
threat precision
self-model recurrence
state_dwell_time = duration(system ∈ attractor_i)
recovery_latency = t_return_to_baseline - t_perturbation
C_exit(x₀ → x_target) = min_u ∫ [||x(t)-x_target||² + λ||u(t)||²]dt
R_self = P(s_{t+1} ∈ self_model_loop | s_t ∈ self_model_loop)
No diagnostic or treatment claims.''')
if __name__=='__main__':main()