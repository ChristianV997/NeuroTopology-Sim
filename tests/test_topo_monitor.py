import numpy as np
from topo_monitor.graph_persistence import analyze_adjacency,reorder_invariant
from topo_monitor.spatial_phase import spatial_winding_charge
from topo_monitor.anomaly_detection import consensus_residual,rolling_alerts

def ring(n=8):
 a=np.zeros((n,n))
 for i in range(n): a[i,(i+1)%n]=a[(i+1)%n,i]=.95
 for i in range(n): a[i,(i+2)%n]=a[(i+2)%n,i]=.8
 np.fill_diagonal(a,1); return a

def test_graph_persistence_finite_and_reorder_invariant():
 r=analyze_adjacency(ring(),threshold=.5); assert r.diagram_h1.ndim==2 and r.landscape.shape==(5,101); assert np.all(np.isfinite(r.beta_curve)); assert reorder_invariant(ring(),np.arange(8)[::-1])
def test_spatial_winding_and_consensus():
 y,x=np.mgrid[-1.01:0.99:65j,-1.01:0.99:65j]; assert abs(spatial_winding_charge(np.arctan2(y,x),np.stack([x,y],axis=-1)))==1
 assert consensus_residual(np.ones((3,3))-np.eye(3),np.ones(3))<1e-12
def test_anomaly_alerts():
 assert rolling_alerts(np.r_[np.zeros(20),np.ones(2)*10],window=10,z_threshold=3)
