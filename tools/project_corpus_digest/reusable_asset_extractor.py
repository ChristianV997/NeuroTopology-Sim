def extract_candidates(row:dict)->list[str]:
    c=[]
    p=row.get('path','').lower()
    if p.endswith('.tex') or p.endswith('.md'): c.append('writing_template')
    if 'config' in p or p.endswith('.yaml'): c.append('config_pattern')
    if p.endswith('.py'): c.append('automation_script')
    return c
