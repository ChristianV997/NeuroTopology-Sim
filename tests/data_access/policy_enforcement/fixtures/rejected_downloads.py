import boto3
import subprocess
import urllib.request


def download(bucket, key, destination, url):
    client = boto3.client("s3")
    client.download_file(bucket, key, destination)
    subprocess.run(["aws", "s3", "sync", "s3://" + bucket, destination], check=True)
    return urllib.request.urlopen(url)
