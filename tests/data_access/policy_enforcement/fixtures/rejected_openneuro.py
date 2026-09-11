import subprocess


def fetch(dataset, output):
    return subprocess.run(["openneuro", "download", dataset, output], check=True)
