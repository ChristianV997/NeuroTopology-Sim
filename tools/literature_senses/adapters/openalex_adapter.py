from .base import BaseAdapter
import json
class OpenAlexAdapter(BaseAdapter):
    def source_id(self): return 'openalex'
    def build_query_url(self, query_pack, max_results): return f"https://api.openalex.org/works?search={query_pack}&per-page={max_results}"
    def parse_response(self, raw): return json.loads(raw).get('results',[])
