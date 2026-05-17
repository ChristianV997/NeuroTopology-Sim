from __future__ import annotations

def classify_claim(text:str):
    l=text.lower(); unsafe=[]
    if any(k in l for k in ['phase conjugate trauma deletion','guaranteed healing','proof of immortality','instant arhat','clinical bypass']):
        return 'unsafe_or_requires_rewrite','unsafe_until_rewritten',True,['unsafe']
    if any(k in l for k in ['soul is real','theory validated','proves','karmic deletion','immortal','vacuum','topological braid','instant arhat']):
        return 'speculative_quarantined','quarantine_only',True,['speculative']
    if any(k in l for k in ['qabs','fdress',' pci','pcist','lzc','entropy','anesthesia','eeg','meg','lfp','criticality','q ']):
        return 'research_hypothesis','research_hypothesis',False,unsafe
    if any(k in l for k in ['dukkha','exit cost','cheap exits','taṇhā','upādāna','anattā','anatta','anicca','lock-in','state-grasping']):
        return 'book_safe_core','book_safe',False,unsafe
    return 'book_safe_core','metaphor_only',False,unsafe
