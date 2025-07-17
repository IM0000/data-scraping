#!/usr/bin/env python3
"""
로컬 테스트용 스크래핑 스크립트
"""
import json
import sys
import time

def main():
    input_data = sys.stdin.read()
    params = json.loads(input_data) if input_data.strip() else {}
    time.sleep(params.get("delay", 0.1))
    print(json.dumps({
        "result": "ok",
        "params": params,
        "timestamp": time.time()
    }))

if __name__ == "__main__":
    main()