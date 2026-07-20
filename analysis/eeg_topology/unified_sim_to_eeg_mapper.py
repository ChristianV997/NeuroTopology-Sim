import numpy as np
import qutip as qt
import matplotlib.pyplot as plt
from scipy.spatial.distance import pdist, squareform
from sklearn.cluster import DBSCAN
from sklearn.manifold import TSNE

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


def run_simulator(N=8, steps=1200, dt=0.06):
    controller = ActiveInferenceController()
    pump_rate = 0.22
    H, c_ops, sx = create_unified_lattice(N=N, pump_rate=pump_rate)
    rho = qt.ket2dm(qt.tensor([qt.basis(2,0) for _ in range(N)]))
    
    coherence_series = []
    for step in range(steps):
        result = qt.mesolve(H, rho, [0, dt], c_ops, e_ops=[])
        rho = result.states[-1]
        
        if step % 30 == 0 or step == steps-1:
            coh = np.mean([abs(qt.expect(sx[i], rho)) for i in range(N)])
            coherence_series.append(coh)
            
            cost = controller.compute_cost(8 - coh*8, np.var(coherence_series[-30:]) if len(coherence_series)>30 else 1.0)
            pump_rate = controller.suggest_pump_rate(cost, base_pump=pump_rate)
            H, c_ops, sx = create_unified_lattice(N=N, pump_rate=pump_rate)
    
    return np.array(coherence_series)


def time_delay_embedding(signal, emb_dim=3, delay=8):
    N = len(signal)
    emb = np.zeros((N - (emb_dim-1)*delay, emb_dim))
    for i in range(emb_dim):
        emb[:, i] = signal[i*delay : i*delay + emb.shape[0]]
    return emb


def mapper_graph(point_cloud, n_cubes=8, eps=0.7):
    if len(point_cloud) < 20:
        return {"nodes": 0, "links": 0}
    lens = TSNE(n_components=2, perplexity=30, random_state=42).fit_transform(point_cloud)
    intervals = [np.linspace(lens.min(0)[i], lens.max(0)[i], n_cubes+1) for i in range(2)]
    nodes = {}
    node_id = 0
    links = set()
    for i in range(n_cubes):
        for j in range(n_cubes):
            mask = ((lens[:,0] >= intervals[0][i]) & (lens[:,0] < intervals[0][i+1]) &
                    (lens[:,1] >= intervals[1][j]) & (lens[:,1] < intervals[1][j+1]))
            if np.sum(mask) < 6: continue
            cluster = DBSCAN(eps=eps, min_samples=3).fit(point_cloud[mask])
            for label in np.unique(cluster.labels_):
                if label == -1: continue
                nodes[node_id] = np.where(mask)[0][cluster.labels_ == label]
                node_id += 1
    for a in nodes:
        for b in nodes:
            if a >= b: continue
            ca = np.mean(point_cloud[nodes[a]], axis=0)
            cb = np.mean(point_cloud[nodes[b]], axis=0)
            if np.linalg.norm(ca - cb) < 1.3*eps:
                links.add((a,b))
    return {"nodes": len(nodes), "links": len(links)}


if __name__ == "__main__":
    print("Running Coupled Unified Simulator → EEG Mapper...")
    coherence_signal = run_simulator(N=10, steps=1400)
    cloud = time_delay_embedding(coherence_signal, emb_dim=3, delay=6)
    mapper_res = mapper_graph(cloud)
    print(f"Final Coherence: {coherence_signal[-1]:.3f}")
    print(f"Mapper Nodes: {mapper_res['nodes']}")
    print(f"Mapper Links: {mapper_res['links']}")