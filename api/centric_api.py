#!/usr/bin/env python3

import argparse
import json
import os
import sys
import base64
from datetime import datetime, timezone
from configparser import ConfigParser
from pathlib import Path
from typing import Optional, Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:  # Python 3.11+
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # Fallback if running on <3.11 with tomli installed
    tomllib = None  # type: ignore[assignment]


def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_centric_config(env_file: Path) -> dict:
    cfg: dict = {}
    if env_file.is_file():
        parser = ConfigParser()
        # Allow keys without explicit section by injecting a default
        with open(env_file, "r", encoding="utf-8") as f:
            content = f.read()
        parser.read_string("""
[DEFAULT]
""" + content)
        if parser.has_section("centric_api"):
            sect = parser["centric_api"]
            if sect.get("base_url"):
                cfg["BASE_URL"] = sect.get("base_url")
            if sect.get("username"):
                cfg["USERNAME"] = sect.get("username")
            if sect.get("password"):
                cfg["PASSWORD"] = sect.get("password")
            if sect.get("default_endpoint"):
                cfg["DEFAULT_ENDPOINT"] = sect.get("default_endpoint")
    return cfg


def load_aliases(aliases_file: Path) -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    if not aliases_file.is_file():
        return aliases
    if tomllib is None:
        # Lazy import tomli if available
        try:
            import tomli  # type: ignore
        except ModuleNotFoundError:
            return aliases
        else:
            with open(aliases_file, "rb") as f:
                data = tomli.load(f)  # type: ignore
    else:
        with open(aliases_file, "rb") as f:
            data = tomllib.load(f)  # type: ignore
    table = data.get("aliases") if isinstance(data, dict) else None
    if isinstance(table, dict):
        for k, v in table.items():
            if isinstance(k, str) and isinstance(v, str) and v.startswith("http"):
                aliases[k.strip()] = v.strip()
    return aliases


def _redact_headers(headers: Dict[str, str]) -> Dict[str, str]:
    redacted: Dict[str, str] = {}
    for k, v in headers.items():
        if k.lower() == "authorization":
            redacted[k] = "Bearer ***"
        else:
            redacted[k] = v
    return redacted


def _bytes_to_safe_text(data: Optional[bytes]) -> str:
    if data is None:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return "base64:" + base64.b64encode(data).decode("ascii")


def write_log(log_file: Path, *, phase: str, method: str, url: str, request_headers: Dict[str, str], request_body: Optional[bytes], response_status: Optional[int] = None, response_headers: Optional[Dict[str, str]] = None, response_body: Optional[bytes] = None, note: Optional[str] = None) -> None:
    try:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"=== {timestamp} | {phase} ===\n")
            f.write(f"Method: {method}\n")
            f.write(f"URL: {url}\n")
            if note:
                f.write(f"Note: {note}\n")
            f.write("Request-Headers: " + json.dumps(_redact_headers(request_headers)) + "\n")
            if request_body is not None:
                f.write("Request-Body: " + _bytes_to_safe_text(request_body) + "\n")
            if response_status is not None:
                f.write(f"Response-Status: {response_status}\n")
            if response_headers is not None:
                try:
                    f.write("Response-Headers: " + json.dumps(dict(response_headers)) + "\n")
                except Exception:
                    f.write("Response-Headers: <unserializable>\n")
            if response_body is not None:
                f.write("Response-Body: " + _bytes_to_safe_text(response_body) + "\n")
            f.write("\n")
    except Exception:
        # Logging must never break the main flow
        pass


def http_request_with_meta(url: str, method: str, headers: Dict[str, str], data: Optional[bytes] = None, timeout: float = 30.0):
    req = Request(url=url, method=method.upper(), data=data)
    for k, v in headers.items():
        req.add_header(k, v)
    if "User-Agent" not in headers:
        req.add_header("User-Agent", "centric-api-client/1.0 (python-stdlib)")
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        return resp.getcode(), dict(resp.headers.items()), body


def build_json_body(username: str, password: str) -> bytes:
    body = json.dumps({"username": username, "password": password}).encode("utf-8")
    return body


def http_request(url: str, method: str, headers: Dict[str, str], data: Optional[bytes] = None, timeout: float = 30.0) -> bytes:
    req = Request(url=url, method=method.upper(), data=data)
    for k, v in headers.items():
        req.add_header(k, v)
    if "User-Agent" not in headers:
        req.add_header("User-Agent", "centric-api-client/1.0 (python-stdlib)")
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def get_token(base_url: str, username: str, password: str, timeout: float = 30.0) -> str:
    auth_url = f"{base_url.rstrip('/')}/csi-requesthandler/api/v2/session"
    headers = {"Content-Type": "application/json"}
    body = build_json_body(username, password)
    raw = http_request(auth_url, "POST", headers, body, timeout=timeout)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        raise RuntimeError(f"Authentication response was not JSON: {raw!r}")
    token_value = str(payload.get("token", "")).strip()
    # If token is like key=value, take the RHS
    if "=" in token_value:
        parts = token_value.split("=", 1)
        token_value = parts[1]
    if not token_value:
        raise RuntimeError(f"Authentication failed, response: {json.dumps(payload)}")
    return token_value


def main() -> int:
    parser = argparse.ArgumentParser(description="Centric API helper (Python)")
    parser.add_argument("-b", "--base-url", dest="base_url")
    parser.add_argument("-u", "--username", dest="username")
    parser.add_argument("-p", "--password", dest="password")
    parser.add_argument("-e", "--endpoint", dest="endpoint", help="Versioned endpoint, e.g. v2/materials")
    parser.add_argument("-m", "--method", dest="method", default="GET")
    parser.add_argument("-d", "--data", dest="data")
    parser.add_argument("-o", "--out", dest="out_file")
    parser.add_argument("--raw", dest="raw", action="store_true", help="Do not pretty print JSON")
    parser.add_argument("--token-only", dest="token_only", action="store_true", help="Print token and exit")
    parser.add_argument("--env-file", dest="env_file", default=str(Path(__file__).parent / ".env"))
    parser.add_argument("--aliases-file", dest="aliases_file", default=str(Path(__file__).parent / "aliases.toml"), help="Path to TOML aliases file")
    parser.add_argument("--alias", dest="alias_name", help="Alias name to use (e.g., materials)")
    parser.add_argument("--log-file", dest="log_file", default=str(Path(__file__).parent / "centric_api.log"), help="Path to append request/response logs")
    parser.add_argument("--token", dest="token")
    parser.add_argument("--token-file", dest="token_file", default=str(Path(__file__).parent / ".token"), help="Path to token cache file")
    parser.add_argument("--timeout", dest="timeout", type=float, default=30.0, help="HTTP timeout in seconds (default: 30)")

    # Capture unknown args to allow alias style like `-materials`
    args, unknown = parser.parse_known_args()

    # Load from .env [centric_api]
    cfg = load_centric_config(Path(args.env_file))

    # Environment variables override file defaults
    base_url = args.base_url or os.environ.get("BASE_URL") or cfg.get("BASE_URL")
    username = args.username or os.environ.get("USERNAME") or cfg.get("USERNAME")
    password = args.password or os.environ.get("PASSWORD") or cfg.get("PASSWORD")
    endpoint = args.endpoint or os.environ.get("DEFAULT_ENDPOINT") or cfg.get("DEFAULT_ENDPOINT")

    # Load aliases and resolve alias if provided
    aliases = load_aliases(Path(args.aliases_file))
    alias_flag: Optional[str] = None
    # 1) explicit --alias <name>
    if args.alias_name:
        alias_flag = args.alias_name.strip().lstrip("-")
    # 2) unknown long flag like --materials
    if not alias_flag:
        for item in unknown:
            if item.startswith("--") and len(item) > 2:
                alias_flag = item.lstrip("-")
    # 3) rescue: if -materials was parsed as -m "aterials", reinterpret when it matches an alias
    valid_methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
    if not alias_flag and args.method and args.method.upper() not in valid_methods:
        possible = args.method.strip().lstrip("-").lower()
        if possible in aliases:
            alias_flag = possible
            args.method = "GET"

    # Resolve token: explicit flag/env, cached file, or authenticate
    token: Optional[str] = args.token or os.environ.get("TOKEN")
    token_file_path = Path(args.token_file)
    if not token and token_file_path.is_file():
        try:
            token = token_file_path.read_text(encoding="utf-8").strip()
        except OSError:
            token = None

    def authenticate_and_cache() -> str:
        nonlocal token
        if not base_url or not username or not password:
            print("Error: base_url, username, and password are required to authenticate (flags, env vars, or .env)", file=sys.stderr)
            raise SystemExit(1)
        try:
            token = get_token(base_url, username, password, timeout=args.timeout)
        except (HTTPError, URLError, RuntimeError) as exc:
            print(f"Authentication failed: {exc}", file=sys.stderr)
            raise SystemExit(1)
        try:
            token_file_path.write_text(token, encoding="utf-8")
        except OSError:
            # Non-fatal if we cannot cache
            pass
        return token

    def ensure_token() -> str:
        nonlocal token
        if token:
            return token
        return authenticate_and_cache()

    if args.token_only:
        print(ensure_token())
        return 0

    # Determine request URL
    req_url: Optional[str] = None
    if alias_flag:
        alias_url = aliases.get(alias_flag)
        if alias_url:
            req_url = alias_url
        else:
            # Fall back strictly to DEFAULT_ENDPOINT if alias not found
            endpoint = cfg.get("DEFAULT_ENDPOINT") or os.environ.get("DEFAULT_ENDPOINT") or endpoint
    if req_url is None:
        if not endpoint:
            print("Error: endpoint is required (-e/--endpoint or DEFAULT_ENDPOINT)", file=sys.stderr)
            return 1
        if not base_url:
            print("Error: base_url is required to build request URL", file=sys.stderr)
            return 1
        req_url = f"{base_url.rstrip('/')}/csi-requesthandler/api/{endpoint.lstrip('/')}"

    headers: Dict[str, str] = {
        "Authorization": f"Bearer {ensure_token()}",
        "Content-Type": "application/json",
    }

    data_bytes: Optional[bytes] = None
    if args.data:
        data_str = args.data
        if data_str.startswith("@"):
            data_str = read_file(data_str[1:])
        data_bytes = data_str.encode("utf-8")

    def perform_request_with_refresh() -> bytes:
        try:
            write_log(Path(args.log_file), phase="REQUEST", method=args.method, url=req_url, request_headers=headers, request_body=data_bytes)
            status, resp_headers, body = http_request_with_meta(req_url, args.method, headers, data_bytes, timeout=args.timeout)
            write_log(Path(args.log_file), phase="RESPONSE", method=args.method, url=req_url, request_headers=headers, request_body=data_bytes, response_status=status, response_headers=resp_headers, response_body=body)
            return body
        except HTTPError as exc:
            if exc.code == 401:
                # Force re-authenticate and retry once
                new_token = authenticate_and_cache()
                headers["Authorization"] = f"Bearer {new_token}"
                # Log original failure
                err_body = None
                try:
                    err_body = exc.read()
                except Exception:
                    pass
                write_log(Path(args.log_file), phase="ERROR", method=args.method, url=req_url, request_headers=headers, request_body=data_bytes, response_status=exc.code, response_body=err_body, note="401 -> retrying after re-auth")
                # Retry
                write_log(Path(args.log_file), phase="REQUEST", method=args.method, url=req_url, request_headers=headers, request_body=data_bytes, note="retry")
                status, resp_headers, body = http_request_with_meta(req_url, args.method, headers, data_bytes, timeout=args.timeout)
                write_log(Path(args.log_file), phase="RESPONSE", method=args.method, url=req_url, request_headers=headers, request_body=data_bytes, response_status=status, response_headers=resp_headers, response_body=body, note="retry")
                return body
            raise
        except URLError as exc:
            write_log(Path(args.log_file), phase="ERROR", method=args.method, url=req_url, request_headers=headers, request_body=data_bytes, note=f"URLError: {exc}")
            raise

    try:
        raw = perform_request_with_refresh()
    except (HTTPError, URLError) as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1

    out_file = args.out_file or "payload.json"
    if out_file:
        if args.raw:
            Path(out_file).write_bytes(raw)
        else:
            try:
                obj = json.loads(raw)
                Path(out_file).write_text(json.dumps(obj, indent=2), encoding="utf-8")
            except json.JSONDecodeError:
                Path(out_file).write_bytes(raw)
        print(f"Wrote response to {out_file}")
        return 0

    if args.raw:
        sys.stdout.buffer.write(raw)
    else:
        try:
            obj = json.loads(raw)
            print(json.dumps(obj, indent=2))
        except json.JSONDecodeError:
            sys.stdout.buffer.write(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


