import argparse
from pathlib import Path

from config import EVENT_LOG_PATH
from database import fetch_all_members, init_db


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="View enrolled members and recent access logs.")
    parser.add_argument("--show-logs", action="store_true", help="Show recent access events from events.log")
    parser.add_argument("--limit", type=int, default=20, help="Number of recent log lines to show")
    return parser.parse_args()


def show_members() -> None:
    members = fetch_all_members()
    print("\n=== ENROLLED MEMBERS ===")
    if not members:
        print("No members found.")
        return

    for member_id, name, _ in members:
        print(f"- {member_id}: {name}")


def show_logs(limit: int) -> None:
    print("\n=== RECENT ACCESS LOGS ===")
    log_path = Path(EVENT_LOG_PATH)
    if not log_path.exists():
        print("No log file found yet.")
        return

    lines = log_path.read_text(encoding="utf-8").splitlines()
    recent_lines = lines[-limit:]
    if not recent_lines:
        print("Log file is empty.")
        return

    for line in recent_lines:
        print(line)


def main() -> None:
    args = parse_args()
    init_db()
    show_members()

    if args.show_logs:
        show_logs(args.limit)


if __name__ == "__main__":
    main()
