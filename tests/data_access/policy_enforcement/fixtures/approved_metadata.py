import urllib.request


def metadata_inventory(url):
    request = urllib.request.Request(url, method="HEAD")
    return urllib.request.urlopen(request, timeout=5)
