from pathlib import Path
import json
from .base import BaseAdapter
class LocalFixtureAdapter(BaseAdapter):
    def source_id(self): return "local_fixture"
    def build_query_url(self, query_pack, max_results): return "fixture://local"
    def parse_response(self, raw): return raw
    def load(self):
        p=Path('tests/fixtures/literature_senses/local_fixture_papers.json')
        return json.loads(p.read_text(encoding='utf-8'))
