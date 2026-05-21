from .base import BaseAdapter
import json
class SemanticScholarAdapter(BaseAdapter):
    def source_id(self): return 'semantic_scholar'
    def build_query_url(self, query_pack, max_results): return f"https://api.semanticscholar.org/graph/v1/paper/search?query={query_pack}&limit={max_results}"
    def parse_response(self, raw): return json.loads(raw).get('data',[])
