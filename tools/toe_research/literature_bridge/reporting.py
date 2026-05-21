import argparse
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    Path(a.out).write_text("\n".join([f"{i}. section" for i in range(1,16)]))
if __name__=='__main__':main()
