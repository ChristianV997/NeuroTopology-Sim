from .base import BaseAdapter
import xml.etree.ElementTree as ET
class PubMedAdapter(BaseAdapter):
    def source_id(self): return 'pubmed'
    def build_query_url(self, query_pack, max_results): return f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={query_pack}&retmax={max_results}"
    def parse_response(self, raw):
        root=ET.fromstring(raw)
        return [{'pmid':(x.text or '')} for x in root.findall('.//Id')]
