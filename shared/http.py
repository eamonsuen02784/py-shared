"""
Shared HTTP client with consistent error handling.

Usage:
    from shared.http import APIClient

    client = APIClient(
        headers={"User-Agent": "...", "Referer": "..."},
        timeout=15,
    )
    data, ok = client.get("https://api.example.com/endpoint", params={"key": "val"})
    if ok:
        print(data)
"""

import requests


class APIClient:
    def __init__(self, headers: dict | None = None, timeout: int = 15):
        self.headers = headers or {}
        self.timeout = timeout

    def get(self, url: str, params: dict | None = None) -> tuple[any, bool]:
        """GET request. Returns (parsed_json, success). On failure returns ({}, False)."""
        try:
            r = requests.get(url, params=params, headers=self.headers, timeout=self.timeout)
            r.raise_for_status()
            return r.json(), True
        except Exception as e:
            print(f"  GET {url} failed: {e}")
            return {}, False

    def post(self, url: str, payload: dict | None = None) -> tuple[dict, bool]:
        """POST request. Returns (parsed_json, success). On failure returns ({}, False)."""
        try:
            r = requests.post(url, json=payload, headers=self.headers, timeout=self.timeout)
            r.raise_for_status()
            return r.json(), True
        except Exception as e:
            print(f"  POST {url} failed: {e}")
            return {}, False
