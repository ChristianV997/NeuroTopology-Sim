import numpy as np
import qutip as qt
import matplotlib.pyplot as plt
from scipy.spatial.distance import pdist, squareform
from typing import Dict

class ActiveInferenceController:
    def __init__(self, precision=1.18, target_beta1=0.8):
        self.precision = precision
        self.target_beta1 = target_beta1

    def compute_cost(self, beta1, q_abs):
        return beta1 + 0.6 * q_abs

    def suggest_pump_rate(self, cost, base_pump=0.25):
        adjustment = self.precision * (cost - self.target_beta1)
        return float(np.clip(base_pump - 0.18 * adjustment, 0.08, 0.85))


def create_unified_lattice(N=8, pump_rate=0.25, chi=0.18):
    si = [qt.qeye(2) for _ in range(N)]
    sx = [qt.tensor(si[:i] + [qt.sigmax()] + si[i+1:]) for i in range(N)]
    sz = [qt.tensor(si[:i] + [qt.sigmaz()] + si[i+1:]) for i in range(N)]

    H = sum(0.5 * sz[i] for i in range(N))
    H += sum(1.0 * (sx[i] * sx[(i+1)%N] + sx[i] * sx[(i-1)%N]) for i in range(N))
    H += pump_rate * sum(sx)
    H += chi * (sum(sx))**2

    c_ops = [np.sqrt(0.12) * sz[i] for i in range(N)]
    for i in range(N):
        c_ops.append(np.sqrt(0.008) * (sz[i] - 0.5))

    return H, c_ops, sx


def run_unified_with_entropy(N=8, steps=1400, dt=0.06, tda_interval=50):
    controller = ActiveInferenceController()
    pump_rate = 0.22
    H, c_ops, sx = create_unified_lattice(N=N, pump_rate=pump_rate)
    rho = qt.ket2dm(qt.tensor([qt.basis(2,0) for _ in range(N)]))
    
    times, coherence, beta1s, qabss, pump_history, entropy_prod = [], [], [], [], [], []
    prev_S = qt.entropy_vn(rho)
    
    for step in range(steps):
        result = qt.mesolve(H, rho, [0, dt], c_ops, e_ops=[])
        rho = result.states[-1]
        
        if step % tda_interval == 0 or step == steps-1:
            t = step * dt
            times.append(t)
            
            coh = np.mean([abs(qt.expect(sx[i], rho)) for i in range(N)])
            coherence.append(coh)
            
            feats = np.array([qt.expect(qt.basis(2,1)*qt.basis(2,1).dag(), rho.ptrace(i)) for i in range(N)])
            feats = np.append(feats, coh)
            dist = squareform(pdist(feats.reshape(1,-1)))
            L = np.diag(np.sum((dist < 0.8).astype(int),0)) - (dist < 0.8).astype(int)
            eig = np.sort(np.real(np.linalg.eigvalsh(L)))
            beta1 = max(0, int(np.sum(eig < 1e-3)-1))
            qabs = float(np.sum(eig[eig<0.5]))
            
            beta1s.append(beta1)
            qabss.append(qabs)
            
            cost = controller.compute_cost(beta1, qabs)
            pump_rate = controller.suggest_pump_rate(cost, base_pump=pump_rate)
            pump_history.append(pump_rate)
            H, c_ops, sx = create_unified_lattice(N=N, pump_rate=pump_rate)
            
            curr_S = qt.entropy_vn(rho)
            dS = curr_S - prev_S
            heat = sum(qt.expect(op.dag()*op, rho) for op in c_ops)
            sigma = -dS/dt + 0.5*heat
            entropy_prod.append(max(0.0, sigma))
            prev_S = curr_S
    
    return {
        "time": np.array(times),
        "coherence": np.array(coherence),
        "beta1": np.array(beta1s),
        "Q_abs": np.array(qabss),
        "pump_rate": np.array(pump_history),
        "entropy_prod": np.array(entropy_prod)
    }


if __name__ == "__main__":
    print("Running Unified Nonlinear Fröhlich + DP + Active Inference + TDA + Entropy Production...")
    res = run_unified_with_entropy(N=10, steps=1600)
    print(f"Final Coherence: {res['coherence'][-1]:.3f}")
    print(f"Final β₁: {res['beta1'][-1]}")
    print(f"Mean Entropy Prod ˙Σ: {np.mean(res['entropy_prod']):.4f}")