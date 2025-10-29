import sys
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


def find_file_pairs(directory: Path) -> List[Tuple[Path, Path, str]]:
    """
    Find pairs of Excel files in the given directory where the base naming matches
    the pattern `<name>_eans.xlsx` and `<name>_orders.xlsx`.

    Returns list of tuples: (eans_path, orders_path, base_name)
    where base_name is `<name>` used for output `<name>_urls.xlsx`.
    """
    eans_files: Dict[str, Path] = {}
    orders_files: Dict[str, Path] = {}

    for path in directory.glob("*.xlsx"):
        name = path.stem
        lower = name.lower()
        if lower.endswith("_eans"):
            base = name[: -len("_eans")]
            eans_files[base] = path
        elif lower.endswith("_orders"):
            base = name[: -len("_orders")]
            orders_files[base] = path

    pairs: List[Tuple[Path, Path, str]] = []
    for base, eans_path in eans_files.items():
        orders_path = orders_files.get(base)
        if orders_path is not None:
            pairs.append((eans_path, orders_path, base))

    return pairs


def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def get_column(df: pd.DataFrame, preferred_names: List[str], fallback_index: int) -> pd.Series:
    """
    Try to get a column by any of the preferred names (case-insensitive).
    If not found, return the column at fallback_index (0-based) if available.
    """
    lower_map = {str(c).strip().lower(): c for c in df.columns}
    for name in preferred_names:
        key = name.lower()
        if key in lower_map:
            return df[lower_map[key]]
    # Fallback by position
    if 0 <= fallback_index < df.shape[1]:
        return df.iloc[:, fallback_index]
    raise KeyError(f"Could not find any of {preferred_names} and no fallback column at index {fallback_index}.")


def read_orders(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, dtype=str)
    df = normalize_column_names(df)
    purchase_order = get_column(df, ["purchase_order", "purchase order", "po"], 0)
    product = get_column(df, ["product", "product_code", "sku"], 1)
    base_url = get_column(df, ["base_url", "base url", "url"], 2)
    out = pd.DataFrame({
        "purchase_order": purchase_order.astype(str).str.strip(),
        "product": product.astype(str).str.strip(),
        "base_url": base_url.astype(str).str.strip(),
    })
    # Drop rows missing any critical field
    out = out.replace({"": pd.NA, "nan": pd.NA}).dropna(subset=["purchase_order", "product", "base_url"], how="any")
    return out


def read_eans(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, dtype=str)
    df = normalize_column_names(df)
    product = get_column(df, ["product", "product_code", "sku"], 0)
    ean = get_column(df, ["ean", "barcode"], 1)
    out = pd.DataFrame({
        "product": product.astype(str).str.strip(),
        "ean": ean.astype(str).str.strip(),
    })
    out = out.replace({"": pd.NA, "nan": pd.NA}).dropna(subset=["product", "ean"], how="any")
    return out


def build_urls(orders: pd.DataFrame, eans: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Produce URLs for every matching (order, ean) where product codes match.
    Returns (urls_df, unmatched_orders_df)
    """
    # Normalize product for joining: case-insensitive, strip
    left = orders.copy()
    right = eans.copy()
    left["product_key"] = left["product"].str.strip().str.lower()
    right["product_key"] = right["product"].str.strip().str.lower()

    merged = left.merge(right[["product_key", "ean"]], on="product_key", how="left")

    matched = merged.dropna(subset=["ean"]).copy()
    unmatched = merged[merged["ean"].isna()][["purchase_order", "product", "base_url"]].drop_duplicates()

    # Compose URL: base_url (no trailing slash) + /01/ + ean + /10/ + purchase_order
    def normalize_base(url: str) -> str:
        return str(url).rstrip("/")

    matched["base_url"] = matched["base_url"].map(normalize_base)
    matched["url"] = (
        matched["base_url"].astype(str)
        + "/01/"
        + matched["ean"].astype(str)
        + "/10/"
        + matched["purchase_order"].astype(str)
    )

    result = matched[["purchase_order", "product", "base_url", "ean", "url"]]
    return result.sort_values(["product", "purchase_order", "ean"]).reset_index(drop=True), unmatched.reset_index(drop=True)


def process_pair(eans_path: Path, orders_path: Path, output_path: Path) -> None:
    orders_df = read_orders(orders_path)
    eans_df = read_eans(eans_path)

    urls_df, unmatched_df = build_urls(orders_df, eans_df)

    # Write to Excel with two sheets: urls (main) and unmatched_orders (if any)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        urls_df.to_excel(writer, index=False, sheet_name="urls")
        if not unmatched_df.empty:
            unmatched_df.to_excel(writer, index=False, sheet_name="unmatched_orders")


def main(argv: List[str]) -> int:
    # Work in the script's directory (url-generator-dpp)
    script_dir = Path(__file__).resolve().parent
    pairs = find_file_pairs(script_dir)

    if not pairs:
        print("No matching *_eans.xlsx and *_orders.xlsx pairs found.")
        return 0

    for eans_path, orders_path, base in pairs:
        output_path = script_dir / f"{base}_urls.xlsx"
        print(f"Processing pair: {eans_path.name} + {orders_path.name} -> {output_path.name}")
        try:
            process_pair(eans_path, orders_path, output_path)
            print(f"Wrote: {output_path}")
        except Exception as exc:  # Intentional broad catch to proceed with other pairs
            print(f"Failed processing {base}: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


