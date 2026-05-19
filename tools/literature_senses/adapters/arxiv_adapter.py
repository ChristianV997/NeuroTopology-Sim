from .base import BaseAdapter
import xml.etree.ElementTree as ET
class ArxivAdapter(BaseAdapter):
    def source_id(self): return 'arxiv'
    def build_query_url(self, query_pack, max_results): return f"https://export.arxiv.org/api/query?search_query=all:{query_pack}&max_results={max_results}"
    def parse_response(self, raw):
        root=ET.fromstring(raw)
        return [{'title':(e.find('{http://www.w3.org/2005/Atom}title').text if e.find('{http://www.w3.org/2005/Atom}title') is not None else 'fixture')} for e in root.findall('{http://www.w3.org/2005/Atom}entry')]
