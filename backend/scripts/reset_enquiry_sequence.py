"""Reset the Enq No. counter (enquiry_sequence.last_number).

Usage (PowerShell, from backend/):
  .\\.venv\\Scripts\\python.exe scripts\\reset_enquiry_sequence.py --dry-run
  .\\.venv\\Scripts\\python.exe scripts\\reset_enquiry_sequence.py --to 0
  .\\.venv\\Scripts\\python.exe scripts\\reset_enquiry_sequence.py --to 0 --force

Default --to 0 makes the next lead ENQ-000001. Safe only when the leads
table is empty (or --to stays above the highest existing ENQ number);
otherwise the next inserts collide on the UNIQUE constraint. Direct SQL
fallback:
  SELECT last_number FROM enquiry_sequence;
  SELECT count(*), max(enquiry_number) FROM leads;
  UPDATE enquiry_sequence SET last_number = 0;
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.services.lead_service import enquiry_sequence_info, reset_enquiry_sequence


def main() -> int:
    ap = argparse.ArgumentParser(description="Reset the ENQ counter")
    ap.add_argument("--to", type=int, default=0, help="New last_number (next lead is to+1)")
    ap.add_argument("--force", action="store_true",
                    help="Allow moving below the highest existing ENQ number")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show current state without writing")
    args = ap.parse_args()

    if args.to < 0:
        print("error: --to must be >= 0")
        return 1

    db = SessionLocal()
    try:
        before = enquiry_sequence_info(db)
        print(f"before: last_number={before['last_number']} "
              f"next={before['next_enquiry']} leads={before['leads_count']} "
              f"max={before['max_enquiry']}")
        if args.dry_run:
            print(f"dry-run: would set last_number={args.to} "
                  f"(next=ENQ-{args.to + 1:06d})")
            return 0
        try:
            result = reset_enquiry_sequence(db, args.to, force=args.force)
        except ValueError as exc:
            print(f"blocked: {exc}")
            db.rollback()
            return 1
        db.commit()
        print(f"ok: last_number={result['last_number']} "
              f"next={result['next_enquiry']} leads={result['leads_count']} "
              f"max={result['max_enquiry']}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
