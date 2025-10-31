#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd


def read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_arrays_of_objects(obj: Any, base_path: str = "$") -> List[Tuple[str, List[Dict[str, Any]]]]:
    results: List[Tuple[str, List[Dict[str, Any]]]] = []
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj):
            results.append((base_path, obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            child_path = f"{base_path}.{k}"
            results.extend(find_arrays_of_objects(v, child_path))
    return results


def get_by_path(obj: Any, path: str) -> Any:
    if not path or path == "$":
        return obj
    # simple dot path from root (with optional leading $.)
    parts = [p for p in path.replace("$.", "").split(".") if p]
    cur = obj
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur


def to_dataframe(records: List[Dict[str, Any]], sep: str) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    return pd.json_normalize(records, sep=sep, max_level=None)


def write_excel_single(df: pd.DataFrame, out_path: Path, sheet_name: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)


def write_excel_multi(sheets: List[Tuple[str, pd.DataFrame]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for sheet_name, df in sheets:
            safe_name = sheet_name[-31:] if len(sheet_name) > 31 else sheet_name
            df.to_excel(writer, index=False, sheet_name=safe_name or "data")


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert JSON payload to Excel")
    parser.add_argument("--input", dest="input", default=str(Path(__file__).parent / "payload.json"))
    parser.add_argument("--out", dest="out", default=str(Path(__file__).parent / "payload.xlsx"))
    parser.add_argument("--path", dest="path", help="Dot path to array of objects (e.g., $.data.items)")
    parser.add_argument("--multi", dest="multi", action="store_true", help="Write all arrays of objects to separate sheets")
    parser.add_argument("--sep", dest="sep", default=".", help="Separator for flattened nested keys (default: .)")
    parser.add_argument("--columns", dest="columns", help="Comma-separated list of columns to include")

    args = parser.parse_args()

    input_path = Path(args.input)
    out_path = Path(args.out)

    payload = read_json(input_path)

    if args.multi:
        arrays = find_arrays_of_objects(payload)
        if not arrays:
            # If no arrays of objects, write the whole doc as one-row sheet
            df = pd.json_normalize(payload, sep=args.sep)
            write_excel_single(df, out_path, sheet_name="payload")
            print(f"Wrote {out_path} (sheet: payload)")
            return 0
        sheets: List[Tuple[str, pd.DataFrame]] = []
        for path_str, records in arrays:
            df = to_dataframe(records, sep=args.sep)
            if args.columns:
                cols = [c.strip() for c in args.columns.split(",") if c.strip()]
                existing = [c for c in cols if c in df.columns]
                if existing:
                    df = df[existing]
            # derive sheet name from path
            name = path_str.replace("$.", "").replace("$", "root") or "data"
            sheets.append((name, df))
        write_excel_multi(sheets, out_path)
        print(f"Wrote {out_path} ({len(sheets)} sheets)")
        return 0

    # single sheet mode
    target = payload if not args.path else get_by_path(payload, args.path)
    if isinstance(target, list) and target and all(isinstance(x, dict) for x in target):
        records = target
        sheet_name = (args.path or "data").replace("$.", "").replace("$", "root") or "data"
        df = to_dataframe(records, sep=args.sep)
    else:
        # fallback: try first array of objects anywhere
        arrays = find_arrays_of_objects(payload)
        if arrays:
            path_str, records = arrays[0]
            sheet_name = path_str.replace("$.", "").replace("$", "root") or "data"
            df = to_dataframe(records, sep=args.sep)
        else:
            # write the entire object as a single row
            df = pd.json_normalize(payload, sep=args.sep)
            sheet_name = "payload"

    if args.columns and not df.empty:
        cols = [c.strip() for c in args.columns.split(",") if c.strip()]
        existing = [c for c in cols if c in df.columns]
        if existing:
            df = df[existing]

    write_excel_single(df, out_path, sheet_name=sheet_name)
    print(f"Wrote {out_path} (sheet: {sheet_name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


