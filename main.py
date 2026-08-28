import argparse
import logging
import sys

import config
from client import QBittorrentDriver, QBitAuthError, TaskAddError, QBitClientError
from models import AcquireRequest, TaskStatus
from orchestrator import DownloadOrchestrator


def _progress_printer(status: TaskStatus) -> None:
    pct = status.progress * 100
    speed_kb = status.download_speed / 1024
    print(f"\r  [{pct:5.1f}%] {speed_kb:.0f} KB/s  ETA: {status.eta_seconds}s  ({status.state})",
          end="", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download a torrent via qBittorrent")
    parser.add_argument("url", help="Magnet URI or .torrent URL")
    parser.add_argument("--save-path", default=None,
                        help=f"Download destination (default: {config.DEFAULT_SAVE_PATH})")
    parser.add_argument("--timeout", type=int, default=30,
                        help="Stall timeout in seconds (default: 30)")
    parser.add_argument("--poll-interval", type=int, default=2,
                        help="Poll interval in seconds (default: 2)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )

    save_path = args.save_path or config.DEFAULT_SAVE_PATH

    try:
        driver = QBittorrentDriver(
            host=config.QBIT_HOST,
            port=config.QBIT_PORT,
            username=config.QBIT_USERNAME,
            password=config.QBIT_PASSWORD,
        )
    except QBitAuthError as exc:
        print(f"Authentication failed: {exc}", file=sys.stderr)
        return 1

    request = AcquireRequest(source_url=args.url, save_path=save_path)
    orchestrator = DownloadOrchestrator(driver)

    print(f"Starting download: {args.url}")
    try:
        success = orchestrator.acquire(
            request,
            stall_timeout=args.timeout,
            poll_interval=args.poll_interval,
            progress_callback=_progress_printer,
        )
    except (TaskAddError, QBitClientError) as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1

    print()
    if success:
        print("Download completed successfully.")
        return 0
    else:
        print("Download failed — torrent stalled or was removed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
