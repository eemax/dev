#!/usr/bin/env python3
from pathlib import Path
from typing import Iterable, Tuple

import pandas as pd


def iter_rows_a_to_d(xlsx_path: Path) -> Iterable[Tuple[str, str, str, str]]:
	"""Yield (url, id, type, value) tuples for non-empty rows in columns A-D.

	Skips rows where any of the required fields is missing.
	"""
	df = pd.read_excel(
		xlsx_path,
		header=None,
		usecols="A:D",
		engine="openpyxl",
	)

	# Drop rows that are entirely empty
	df = df.dropna(how="all")

	for _, row in df.iterrows():
		url, id_val, type_val, value_val = row.tolist()
		# Skip rows with any missing required value
		if pd.isna(url) or pd.isna(id_val) or pd.isna(type_val) or pd.isna(value_val):
			continue
		yield (
			str(url).strip(),
			str(id_val).strip(),
			str(type_val).strip(),
			str(value_val).strip(),
		)


def build_change_node(url: str, id_value: str, type_value: str, value: str) -> str:
	return (
		f'<ChangeNode URL="{url}" >\n'
		f'	<ChangeAttribute Id="{id_value}" Type="{type_value}" Value="{value}" />\n'
		f'</ChangeNode>'
	)


def process_excel_file(xlsx_path: Path) -> Path:
	"""Process a single Excel file and write the corresponding XML file.

	The output XML filename matches the Excel filename (with .xml extension).
	"""
	output_path = xlsx_path.with_suffix(".xml")
	lines: list[str] = []
	for url, id_value, type_value, value in iter_rows_a_to_d(xlsx_path):
		lines.append(build_change_node(url, id_value, type_value, value))

	output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
	return output_path


def main() -> None:
	folder = Path(__file__).parent
	patterns = ("*.xlsx", "*.xlsm")
	excel_files: list[Path] = []
	for pattern in patterns:
		excel_files.extend([p for p in folder.glob(pattern) if not p.name.startswith("~$")])

	for xlsx_path in sorted(excel_files):
		xml_path = process_excel_file(xlsx_path)
		print(f"Wrote: {xml_path}")


if __name__ == "__main__":
	main()


