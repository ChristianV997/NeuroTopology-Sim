from __future__ import annotations
FORBIDDEN = ["proves consciousness", "proof of soul", "clinical efficacy proven", "liberation guaranteed", "api key:"]
SAFE_QUALIFIERS = ["hypothesis", "preliminary", "requires validation", "simulated", "non-clinical"]

def analyze_text(text:str):
    out=[]
    lt=text.lower()
    for p in FORBIDDEN:
        if p in lt:
            out.append({"risky_phrase":p,"safe_rewrite":f"Replace '{p}' with a hypothesis-qualified, non-proof statement."})
    return out
