#!/usr/bin/env python3
import sys
import json
import requests

"""
Quick helper to POST JSON to a local endpoint.

Usage:
  ./scripts/post.py http://localhost:8000/webhook '{"hello":"world"}'
  ./scripts/post.py http://localhost:8000/run/taskmaster

If the second argument is missing, an empty JSON object is sent.
"""

def main():
    if len(sys.argv) < 2:
        print("Usage: post.py URL [JSON]", file=sys.stderr)
        sys.exit(1)
    url = sys.argv[1]
    data = {}
    if len(sys.argv) >= 3:
        try:
            data = json.loads(sys.argv[2])
        except Exception as e:
            print(f"Invalid JSON: {e}", file=sys.stderr)
            sys.exit(2)
    try:
        r = requests.post(url, json=data, timeout=15)
        print(f"Status: {r.status_code}")
        print(r.text)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(3)

if __name__ == "__main__":
    main()
