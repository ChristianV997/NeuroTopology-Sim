import json, os, datetime

def read_json(path):
    with open(path,'r',encoding='utf-8') as f:return json.load(f)

def write_json(path,data):
    os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(path,'w',encoding='utf-8') as f: json.dump(data,f,indent=2)

def now_iso(): return datetime.datetime.utcnow().replace(microsecond=0).isoformat()+"Z"
