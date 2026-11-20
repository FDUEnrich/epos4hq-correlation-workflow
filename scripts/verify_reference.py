#!/usr/bin/env python3
"""Verify the immutable downloaded baseline without contacting the server."""
import hashlib
import json
from pathlib import Path


def main():
    repo=Path(__file__).resolve().parents[1]
    manifest=json.loads((repo/'reference/SOURCE_MANIFEST.json').read_text())
    for relative,record in manifest['files'].items():
        actual=hashlib.sha256((repo/relative).read_bytes()).hexdigest()
        if actual!=record['sha256']:raise ValueError('Changed reference: '+relative)
    print('REFERENCE_CHECKSUM_PASS',len(manifest['files']))


if __name__=='__main__':main()
