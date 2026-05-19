def apply_quarantine(row:dict)->dict:
    if row.get('category')=='speculative_ontology':
        row['claim_scope']='ontology_quarantined'
        row.setdefault('safety_notes',[]).append('Quarantined by default; excluded from safe RAG.')
    return row
