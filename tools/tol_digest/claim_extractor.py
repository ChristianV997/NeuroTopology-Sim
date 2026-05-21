from __future__ import annotations
from pathlib import Path
DOCTRINE=['dukkha','taṇhā','tanha','upādāna','upadana','anattā','anatta','anicca','paṭiccasamuppāda','jhāna','arūpa','nibbāna','vimutti','fetters','hindrances']
CONS=['exit cost','lock-in','rigidity','cheap exits','permeability','state-grasping','attractor','hysteresis','fragmentation','residue','defect load']
SCI=['q','qabs','fdress','pci','pcist','lzc','entropy','eeg','meg','lfp','phase field','anesthesia','propofol','ketamine','meditation','criticality','topology']
SPEC=['soul','braid','immortal','validated','proves','karmic deletion','instant','arhat state','vacuum','cosmic','transceiver','grand-parent fossil','phase conjugate trauma deletion']

def extract_claims_from_text(text:str,source_id:str):
    chunks=[c.strip() for c in text.replace('\r','').split('\n') if c.strip()]
    claims=[]; i=0
    for c in chunks:
        l=c.lower()
        if any(k in l for k in DOCTRINE+CONS+SCI+SPEC):
            claims.append({'claim_id':f'{source_id}_c{i:04d}','source_id':source_id,'text':c,'normalized_text':' '.join(l.split())})
            i+=1
    return claims

def extract_claims(sources):
    allc=[]
    for s in sources:
        if s['extension']=='.pdf': continue
        p=Path(s['path'])
        t=p.read_text(encoding='utf-8',errors='ignore') if p.exists() else ''
        allc.extend(extract_claims_from_text(t,s['source_id']))
    return allc
