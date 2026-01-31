# SPDX-FileCopyrightText: 2024-present Guest Database Manager <admin@example.com>
#
# SPDX-License-Identifier: MIT
"""Command-line interface for Guest Database Manager."""

import argparse
import subprocess
import sys
from pathlib import Path

from guest_database_manager.database import GuestDatabase


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

    # Import data
    import_parser = subparsers.add_parser("import", help="Import data from a file")
    import_parser.add_argument("file", type=Path, help="Path to CSV or Excel file to import")
    import_parser.add_argument(
        "--db",
        type=Path,
        default="guest_database_updated.db",
        help="Database file path (default: guest_database_updated.db)",
    )

    # Show stats
    stats_parser = subparsers.add_parser("stats", help="Show database statistics")
    stats_parser.add_argument(
        "--db",
        type=Path,
        default="guest_database_updated.db",
        help="Database file path (default: guest_database_updated.db)",
    )

    # Clean database
    clean_parser = subparsers.add_parser("clean", help="Clean the database")
    clean_parser.add_argument(
        "--db",
        type=Path,
        default="guest_database_updated.db",
        help="Database file path (default: guest_database_updated.db)",
    )

    return parser


def run_streamlit_app(host: str = "localhost", port: int = 8501) -> None:
    """Launch the Streamlit application."""
    try:
        # Get the path to the app module
        app_path = Path(__file__).parent / "app.py"

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

        print(f"🚀 Starting Streamlit app at http://{host}:{port}")
        subprocess.run(cmd, check=False)

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

        if result["success"]:
            print("✅ Import successful!")
            print(f"   New guests: {result['new_guests']}")
            print(f"   Updated guests: {result['updated_guests']}")
            print(f"   Total rows processed: {result['total_processed']}")
        else:
            print(f"❌ Import failed: {result['error']}")
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
        success = db.clean_database()

        if success:
            print("✅ Database cleaned successfully!")
        else:
            print("❌ Failed to clean database")
            sys.exit(1)

    except (OSError, ValueError) as e:
        print(f"❌ Error cleaning database: {e}")
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
    elif args.command == "import":
        import_data(args.file, args.db)
    elif args.command == "stats":
        show_stats(args.db)
    elif args.command == "clean":
        clean_database(args.db)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
