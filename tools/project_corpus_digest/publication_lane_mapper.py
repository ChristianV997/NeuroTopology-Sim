def lane_for(row:dict)->str:
    if row.get('category')=='manuscripts': return 'publication_safe_lane'
    if row.get('category')=='speculative_ontology': return 'quarantine_lane'
    if row.get('category')=='governance': return 'governance_lane'
    return 'internal_engineering_lane'
