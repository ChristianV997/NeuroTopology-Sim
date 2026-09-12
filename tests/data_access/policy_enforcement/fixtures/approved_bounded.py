import urllib.request
import shutil


def bounded_transfer(url, output, byte_range):
    request = urllib.request.Request(url, headers={"Range": byte_range})
    with urllib.request.urlopen(request, timeout=5) as response, output.open("wb") as handle:
        shutil.copyfileobj(response, handle)
