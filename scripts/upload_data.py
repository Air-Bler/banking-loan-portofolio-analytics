"""Upload the landing batches to the Unity Catalog volume and (optionally) run the pipeline.

Uses the Databricks SDK for Python.

Setup (once):
    pip install databricks-sdk
    databricks auth login --host https://<your-workspace>.azuredatabricks.net
        (or set DATABRICKS_HOST and DATABRICKS_TOKEN)

Examples:
    # upload all four batches
    python scripts/upload_data.py --landing data/landing

    # upload all four batches, then run the pipeline once and wait for the result
    python scripts/upload_data.py --landing data/landing --start --wait

    # incremental demo: upload batch_001, run, wait; then batch_002, run, wait; ...
    python scripts/upload_data.py --landing data/landing --each-batch

    # only one batch
    python scripts/upload_data.py --landing data/landing --batches batch_002

Files already in the volume with the same size are skipped, so the script can be rerun safely.
data/generated_metadata/ is never uploaded (the data guide says it must not be ingested).
"""

import argparse
import sys
import time
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound

VOLUME = "/Volumes/data2026acc123456/team2/raw_data"  # must match the path in pipelines/bronze/*.sql
TARGET_FOLDER = "loans"
PIPELINE_NAME = "team2-loan-pipeline"
TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELED"}


def parse_args():
    p = argparse.ArgumentParser(description="Upload landing batches to Databricks and run the pipeline")
    p.add_argument("--landing", default="data/landing", help="local folder holding batch_001 ... batch_004")
    p.add_argument("--volume", default=VOLUME, help="volume root, e.g. /Volumes/<catalog>/<schema>/<volume>")
    p.add_argument("--batches", nargs="*", help="batches to upload (default: every batch_* folder)")
    p.add_argument("--profile", help="profile from ~/.databrickscfg (default: env vars or DEFAULT)")
    p.add_argument("--pipeline-name", default=PIPELINE_NAME)
    p.add_argument("--pipeline-id", help="use this id instead of looking the pipeline up by name")
    p.add_argument("--start", action="store_true", help="start the pipeline after the upload")
    p.add_argument("--wait", action="store_true", help="wait until the pipeline update finishes")
    p.add_argument("--each-batch", action="store_true",
                   help="upload one batch, run the pipeline and wait, then the next batch (implies --start --wait)")
    p.add_argument("--full-refresh", action="store_true", help="full refresh (reloads every file; use only when Bronze changes)")
    return p.parse_args()


def find_batches(landing: Path, wanted):
    if not landing.is_dir():
        sys.exit(f"Landing folder not found: {landing}")
    batches = sorted(d for d in landing.iterdir() if d.is_dir() and d.name.startswith("batch_"))
    if wanted:
        batches = [d for d in batches if d.name in set(wanted)]
        missing = set(wanted) - {d.name for d in batches}
        if missing:
            sys.exit(f"Batch folders not found in {landing}: {', '.join(sorted(missing))}")
    if not batches:
        sys.exit(f"No batch_* folders in {landing}")
    return batches


def check_volume(w: WorkspaceClient, volume: str):
    try:
        w.files.get_directory_metadata(volume)
    except NotFound:
        sys.exit(f"Volume not found or no access: {volume}. Create it in Catalog or fix --volume.")


def remote_size(w: WorkspaceClient, path: str):
    try:
        return w.files.get_metadata(path).content_length
    except NotFound:
        return None


def upload_batch(w: WorkspaceClient, batch_dir: Path, target_root: str):
    target_dir = f"{target_root}/{batch_dir.name}"
    w.files.create_directory(target_dir)          # no error if it already exists
    for f in sorted(p for p in batch_dir.iterdir() if p.is_file()):
        target = f"{target_dir}/{f.name}"
        size = f.stat().st_size
        if remote_size(w, target) == size:
            print(f"  skip      {target} (already there)")
            continue
        print(f"  upload    {target} ({size / 1_048_576:.1f} MB)", flush=True)
        t0 = time.time()
        with open(f, "rb") as fh:
            w.files.upload(target, fh, overwrite=True)  # large files go up in parts automatically
        print(f"            done in {time.time() - t0:.0f}s")


def find_pipeline_id(w: WorkspaceClient, name: str):
    matches = [p for p in w.pipelines.list_pipelines(filter=f"name LIKE '{name}'") if p.name == name]
    if not matches:
        sys.exit(f"Pipeline '{name}' not found. Create it first (see pipelines/README.md) or pass --pipeline-id.")
    if len(matches) > 1:
        ids = ", ".join(p.pipeline_id for p in matches)
        sys.exit(f"More than one pipeline is called '{name}' ({ids}). Pass --pipeline-id.")
    return matches[0].pipeline_id


def run_pipeline(w: WorkspaceClient, pipeline_id: str, full_refresh: bool, wait: bool):
    update = w.pipelines.start_update(pipeline_id, full_refresh=full_refresh)
    print(f"Pipeline update started: {update.update_id}" + (" (full refresh)" if full_refresh else ""))
    if not wait:
        return
    last = None
    while True:
        state = w.pipelines.get_update(pipeline_id, update.update_id).update.state.value
        if state != last:
            print(f"  {time.strftime('%H:%M:%S')}  {state}", flush=True)
            last = state
        if state in TERMINAL_STATES:
            break
        time.sleep(15)
    if state != "COMPLETED":
        sys.exit(f"Pipeline update {update.update_id} ended {state}. Check the event log in the pipeline UI.")


def main():
    args = parse_args()
    if args.each_batch:
        args.start = args.wait = True

    batches = find_batches(Path(args.landing), args.batches)
    w = WorkspaceClient(profile=args.profile) if args.profile else WorkspaceClient()
    print(f"Workspace: {w.config.host}")

    volume = args.volume.rstrip("/")
    check_volume(w, volume)
    target_root = f"{volume}/{TARGET_FOLDER}"
    w.files.create_directory(target_root)

    pipeline_id = None
    if args.start:
        pipeline_id = args.pipeline_id or find_pipeline_id(w, args.pipeline_name)
        print(f"Pipeline: {args.pipeline_name} ({pipeline_id})")

    if args.each_batch:
        for i, b in enumerate(batches):
            print(f"\n{b.name}")
            upload_batch(w, b, target_root)
            # full refresh, if asked, only on the first run; later runs must stay incremental
            run_pipeline(w, pipeline_id, full_refresh=args.full_refresh and i == 0, wait=True)
    else:
        for b in batches:
            print(f"\n{b.name}")
            upload_batch(w, b, target_root)
        if args.start:
            print()
            run_pipeline(w, pipeline_id, full_refresh=args.full_refresh, wait=args.wait)

    print("\nDone.")


if __name__ == "__main__":
    main()
