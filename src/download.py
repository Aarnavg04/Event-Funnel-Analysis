"""Fetch the two source months from Kaggle into DATA_DIR.

Usage:
    .venv/bin/python src/download.py
    .venv/bin/python src/download.py --check   # auth only, no download

Credentials come from .env (KAGGLE_USERNAME / KAGGLE_KEY). Note the import
order below: the Kaggle client reads its credentials from the process
environment at authenticate() time, so load_dotenv() has to run BEFORE the
kaggle package is imported. Importing kaggle at the top of the file, the way
you normally would, authenticates against an environment that does not have the
credentials in it yet and fails with a misleading error.
"""

from __future__ import annotations

import argparse
import sys
import zipfile

from config import DATA_DIR, SOURCE_FILES  # calls load_dotenv() on import

DATASET = "mkechinov/ecommerce-behavior-data-from-multi-category-store"


def api():
    import os

    if not os.getenv("KAGGLE_USERNAME") or not os.getenv("KAGGLE_KEY"):
        sys.exit("FAIL: set KAGGLE_USERNAME and KAGGLE_KEY in .env")

    from kaggle.api.kaggle_api_extended import KaggleApi

    client = KaggleApi()
    client.authenticate()
    return client


def check(client) -> None:
    """Cheap auth + access probe. Run this before a 9 GB download."""
    try:
        files = client.dataset_list_files(DATASET).files
    except Exception as exc:  # noqa: BLE001 - surface the raw message
        sys.exit(
            f"FAIL: {exc}\n\n"
            "A 403 here usually is NOT a bad token -- it means the dataset's "
            "rules have not been accepted. Open the dataset page while logged "
            "in and click through the download prompt once:\n"
            f"  https://www.kaggle.com/datasets/{DATASET}"
        )

    names = {f.name for f in files}
    print(f"  authenticated; dataset exposes {len(names)} files")
    for want in SOURCE_FILES:
        print(f"    [{'ok' if want in names else 'MISSING'}] {want}")
    missing = [w for w in SOURCE_FILES if w not in names]
    if missing:
        sys.exit(f"FAIL: expected files not present in dataset: {missing}")


def download(client) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in SOURCE_FILES:
        target = DATA_DIR / name
        if target.exists():
            print(f"  {name} already present ({target.stat().st_size / 1e9:.2f} GB), skipping")
            continue

        print(f"  downloading {name} ...", flush=True)
        client.dataset_download_file(DATASET, name, path=str(DATA_DIR), force=False)

        # Kaggle serves single files zipped. Unzip and drop the archive so the
        # census in load.py sees a plain CSV.
        archive = DATA_DIR / f"{name}.zip"
        if archive.exists():
            print(f"  unzipping {archive.name} ...", flush=True)
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(DATA_DIR)
            archive.unlink()

        if not target.exists():
            sys.exit(f"FAIL: {name} not present after download.")
        print(f"    {name}: {target.stat().st_size / 1e9:.2f} GB")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="verify auth and access, download nothing")
    args = ap.parse_args()

    client = api()
    check(client)
    if args.check:
        print("\nAuth and access OK. Re-run without --check to download.")
        return
    download(client)
    print("\nDownload complete. Next: .venv/bin/python src/load.py --setup")


if __name__ == "__main__":
    main()
