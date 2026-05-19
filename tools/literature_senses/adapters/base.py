class BaseAdapter:
    def build_query_url(self, query_pack, max_results): raise NotImplementedError
    def parse_response(self, raw): raise NotImplementedError
    def normalize_record(self, record): return record
    def source_id(self): raise NotImplementedError
    def supports_live(self): return False
    def required_env_vars(self): return []
    def legal_notes(self): return "metadata-only and terms-compliant"
