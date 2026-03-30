from __future__ import annotations

import argparse
from contextlib import ExitStack

from maintenance_copilot.api import build_container, load_seed_assets
from maintenance_copilot.config import get_settings
from maintenance_copilot.ingest import load_log_seed, load_manual_seed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="maintenance-copilot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_assets = subparsers.add_parser("seed-assets")
    seed_assets.add_argument("--path", default=None)

    ingest_manual = subparsers.add_parser("ingest-manual")
    ingest_manual.add_argument("--path", required=True)
    ingest_manual.add_argument("--tenant-id", required=True)

    enqueue_manual = subparsers.add_parser("enqueue-manual")
    enqueue_manual.add_argument("--path", required=True)
    enqueue_manual.add_argument("--tenant-id", required=True)

    ingest_log = subparsers.add_parser("ingest-log")
    ingest_log.add_argument("--path", required=True)
    ingest_log.add_argument("--tenant-id", required=True)

    process_jobs = subparsers.add_parser("process-manual-jobs")
    process_jobs.add_argument("--once", action="store_true")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    settings = get_settings()

    with ExitStack() as exit_stack:
        container = build_container(settings, exit_stack=exit_stack)

        if args.command == "seed-assets":
            load_seed_assets(
                container.asset_catalog,
                args.path or settings.local_asset_seed_path,
            )
            return

        if args.command == "ingest-manual":
            request = load_manual_seed(args.path)
            container.manual_ingest.ingest(request, args.tenant_id)
            return

        if args.command == "enqueue-manual":
            request = load_manual_seed(args.path)
            container.manual_job_repo.create(args.tenant_id, request)
            return

        if args.command == "ingest-log":
            request = load_log_seed(args.path)
            container.log_ingest.ingest(request, args.tenant_id)
            return

        if args.command == "process-manual-jobs":
            while True:
                job = container.manual_job_repo.claim_next_pending()
                if job is None:
                    return
                container.manual_job_processor.process(job)
                if args.once:
                    return


if __name__ == "__main__":
    main()
