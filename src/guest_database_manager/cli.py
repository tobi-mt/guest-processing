# SPDX-FileCopyrightText: 2024-present Guest Database Manager <admin@example.com>
#
# SPDX-License-Identifier: MIT
"""Command-line interface for Guest Database Manager."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from guest_database_manager.constants import DEFAULT_DB_PATH
from guest_database_manager.database import GuestDatabase
from guest_database_manager.web_interface import run_web_interface
from guest_database_manager.web_interface import GuestWebService


def create_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(description="Guest Database Manager - Manage guest data from CSV/Excel files")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Run Streamlit app
    app_parser = subparsers.add_parser("app", help="Launch the Streamlit web application")
    app_parser.add_argument("--port", type=int, default=8501, help="Port to run the Streamlit app on (default: 8501)")
    app_parser.add_argument(
        "--host", type=str, default="localhost", help="Host to run the Streamlit app on (default: localhost)"
    )

    web_parser = subparsers.add_parser("web", help="Launch the direct HTML/CSS/JS web interface")
    web_parser.add_argument("--port", type=int, default=8601, help="Port to run the web interface on (default: 8601)")
    web_parser.add_argument(
        "--host", type=str, default="127.0.0.1", help="Host to run the web interface on (default: 127.0.0.1)"
    )
    web_parser.add_argument(
        "--db",
        type=Path,
        default=Path(DEFAULT_DB_PATH),
        help=f"Database file path (default: {DEFAULT_DB_PATH})",
    )
    web_parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start the web interface without opening a browser automatically",
    )

    # Import data
    import_parser = subparsers.add_parser("import", help="Import data from a file")
    import_parser.add_argument("file", type=Path, help="Path to CSV or Excel file to import")
    import_parser.add_argument(
        "--db",
        type=Path,
        default=Path(DEFAULT_DB_PATH),
        help=f"Database file path (default: {DEFAULT_DB_PATH})",
    )

    # Show stats
    stats_parser = subparsers.add_parser("stats", help="Show database statistics")
    stats_parser.add_argument(
        "--db",
        type=Path,
        default=Path(DEFAULT_DB_PATH),
        help=f"Database file path (default: {DEFAULT_DB_PATH})",
    )

    # Clean database
    clean_parser = subparsers.add_parser("clean", help="Clean the database")
    clean_parser.add_argument(
        "--db",
        type=Path,
        default=Path(DEFAULT_DB_PATH),
        help=f"Database file path (default: {DEFAULT_DB_PATH})",
    )

    reminders_parser = subparsers.add_parser("reminders", help="Send weekly interview reminder emails")
    reminders_parser.add_argument(
        "--db",
        type=Path,
        default=Path(DEFAULT_DB_PATH),
        help=f"Database file path (default: {DEFAULT_DB_PATH})",
    )
    reminders_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview which reminders would be sent without sending emails",
    )

    calendar_sync_parser = subparsers.add_parser("calendar-sync", help="Sync Google Calendar interviews into podcast operations")
    calendar_sync_parser.add_argument(
        "--db",
        type=Path,
        default=Path(DEFAULT_DB_PATH),
        help=f"Database file path (default: {DEFAULT_DB_PATH})",
    )
    calendar_sync_parser.add_argument(
        "--days-ahead",
        type=int,
        default=30,
        help="How many days ahead to pull interview events from Google Calendar",
    )
    calendar_sync_parser.add_argument(
        "--query",
        type=str,
        default="",
        help="Optional Google Calendar search query to narrow synced events",
    )
    calendar_sync_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview which calendar events would sync without writing interviews",
    )

    return parser


def run_streamlit_app(host: str = "localhost", port: int = 8501) -> None:
    """Launch the Streamlit application."""
    try:
        # Get the path to the app module
        app_path = Path(__file__).parent / "app.py"
        src_root = app_path.parent.parent

        # Run streamlit
        cmd = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_path),
            "--server.address",
            host,
            "--server.port",
            str(port),
        ]
        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            f"{src_root}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else str(src_root)
        )

        print(f"🚀 Starting Streamlit app at http://{host}:{port}")
        subprocess.run(cmd, check=False, env=env)

    except ImportError:
        print("❌ Streamlit is not installed. Please install it with: pip install streamlit")
        sys.exit(1)
    except (subprocess.SubprocessError, OSError) as e:
        print(f"❌ Error starting Streamlit app: {e}")
        sys.exit(1)


def import_data(file_path: Path, db_path: Path) -> None:
    """Import data from a file."""
    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        sys.exit(1)

    print(f"📁 Importing data from {file_path}")

    try:
        db = GuestDatabase(db_path)
        result = db.add_guest_from_csv(file_path)

        if result["errors"] == 0:
            print("✅ Import successful!")
            print(f"   New guests: {result['imported']}")
            print(f"   Updated guests: {result['updated']}")
            print(f"   Skipped rows: {result['skipped']}")
            print(f"   Errors: {result['errors']}")
        else:
            print("❌ Import completed with errors.")
            print(f"   New guests: {result['imported']}")
            print(f"   Updated guests: {result['updated']}")
            print(f"   Skipped rows: {result['skipped']}")
            print(f"   Errors: {result['errors']}")
            sys.exit(1)

    except (OSError, ValueError) as e:
        print(f"❌ Error during import: {e}")
        sys.exit(1)


def show_stats(db_path: Path) -> None:
    """Show database statistics."""
    try:
        db = GuestDatabase(db_path)
        stats = db.get_guest_stats()

        print("📊 Guest Database Statistics")
        print("=" * 30)
        print(f"Total guests: {stats['total']}")
        print(f"Processed: {stats['processed']}")
        print(f"Unprocessed: {stats['unprocessed']}")

        if stats["total"] > 0:
            completion_rate = (stats["processed"] / stats["total"]) * 100
            print(f"Completion rate: {completion_rate:.1f}%")

    except (OSError, ValueError) as e:
        print(f"❌ Error getting statistics: {e}")
        sys.exit(1)


def clean_database(db_path: Path) -> None:
    """Clean the database."""
    try:
        db = GuestDatabase(db_path)

        print("🧹 Cleaning database...")
        result = db.clean_database()

        if result["removed"] or result["fixed"]:
            print("✅ Database cleaned successfully!")
            print(f"   Duplicates removed: {result['removed']}")
            print(f"   Records fixed: {result['fixed']}")
        else:
            print("ℹ️ Database was already clean.")

    except (OSError, ValueError) as e:
        print(f"❌ Error cleaning database: {e}")
        sys.exit(1)


def send_weekly_reminders(db_path: Path, dry_run: bool = False) -> None:
    """Send or preview weekly interview reminders."""
    try:
        service = GuestWebService(db_path)
        result = service.send_due_weekly_reminders(dry_run=dry_run)

        if dry_run:
            print(f"🗓️ Weekly reminder preview: {result['count']} interview(s) due")
            for interview in result["interviews"]:
                print(f" - {interview['guest_name']} | {interview['scheduled_for_display']}")
            return

        print(f"📨 Sent {result['count']} weekly reminder(s)")
        for sent_interview in result["sent"]:
            print(f" - {sent_interview['guest_name']} | {sent_interview['scheduled_for_display']}")

        if result["errors"]:
            print("⚠️ Some reminders could not be sent:")
            for error in result["errors"]:
                print(f" - {error['guest_name']}: {error['error']}")

    except (OSError, ValueError) as e:
        print(f"❌ Error sending reminders: {e}")
        sys.exit(1)


def sync_google_calendar(db_path: Path, days_ahead: int = 30, query: str = "", dry_run: bool = False) -> None:
    """Sync Google Calendar interviews into the operations tracker."""
    try:
        service = GuestWebService(db_path)
        result = service.sync_google_calendar_interviews(days_ahead=days_ahead, query=query, dry_run=dry_run)

        if dry_run:
            print(f"🗓️ Google Calendar sync preview: {result['count']} interview event(s) found")
        else:
            print(f"🔄 Google Calendar sync complete: {result['count']} interview event(s) synced")

        for interview in result["interviews"]:
            action = interview.get("sync_action", "previewed")
            print(f" - {interview['guest_name']} | {interview['scheduled_for_display']} | {action}")

    except (OSError, ValueError) as e:
        print(f"❌ Error syncing Google Calendar: {e}")
        sys.exit(1)


def main() -> None:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        # Default to running the app
        run_streamlit_app()
        return

    if args.command == "app":
        run_streamlit_app(args.host, args.port)
    elif args.command == "web":
        run_web_interface(args.host, args.port, args.db, open_browser=not args.no_browser)
    elif args.command == "import":
        import_data(args.file, args.db)
    elif args.command == "stats":
        show_stats(args.db)
    elif args.command == "clean":
        clean_database(args.db)
    elif args.command == "reminders":
        send_weekly_reminders(args.db, args.dry_run)
    elif args.command == "calendar-sync":
        sync_google_calendar(args.db, args.days_ahead, args.query, args.dry_run)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
