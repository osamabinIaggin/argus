"""
API key management CLI for Video Intelligence.

Usage:
  python scripts/manage_keys.py create --name "Acme Corp" --plan starter
  python scripts/manage_keys.py list
  python scripts/manage_keys.py revoke vi_live_abc123...
  python scripts/manage_keys.py info vi_live_abc123...
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.auth import create_key, get_key, list_keys, revoke_key


PLANS = ("free", "starter", "pro", "enterprise")

PLAN_LIMITS = {
    "free":       "10 min/month",
    "starter":    "300 min/month",
    "pro":        "1,500 min/month",
    "enterprise": "unlimited",
}


def cmd_create(args: argparse.Namespace) -> None:
    key = create_key(name=args.name, plan=args.plan)
    print()
    print("  API key created successfully")
    print(f"  ─────────────────────────────────────────────────")
    print(f"  Key:      {key.key}")
    print(f"  Name:     {key.name}")
    print(f"  Plan:     {key.plan}  ({PLAN_LIMITS[key.plan]})")
    print(f"  Created:  {key.created_at.strftime('%Y-%m-%d %H:%M UTC')}")
    print()
    print("  Store this key securely — it cannot be recovered if lost.")
    print()


def cmd_list(args: argparse.Namespace) -> None:
    keys = list_keys()
    if not keys:
        print("No API keys in database.")
        return

    header = f"  {'Key':<42}  {'Name':<22}  {'Plan':<12}  {'Requests':>9}  {'Active'}"
    print()
    print(header)
    print("  " + "─" * 98)
    for k in keys:
        active = "yes" if k.is_active else "REVOKED"
        last = k.last_used_at.strftime("%Y-%m-%d") if k.last_used_at else "never"
        print(f"  {k.key:<42}  {k.name:<22}  {k.plan:<12}  {k.total_requests:>9}  {active}  (last: {last})")
    print()
    print(f"  Total: {len(keys)} key(s)")
    print()


def cmd_revoke(args: argparse.Namespace) -> None:
    if revoke_key(args.key):
        print(f"  Revoked: {args.key}")
    else:
        print(f"  Key not found: {args.key}")
        sys.exit(1)


def cmd_info(args: argparse.Namespace) -> None:
    key = get_key(args.key)
    if not key:
        print(f"  Key not found: {args.key}")
        sys.exit(1)
    print()
    print(f"  Key:       {key.key}")
    print(f"  Name:      {key.name}")
    print(f"  Plan:      {key.plan}  ({PLAN_LIMITS.get(key.plan, 'unknown')})")
    print(f"  Active:    {'yes' if key.is_active else 'REVOKED'}")
    print(f"  Requests:  {key.total_requests:,}")
    print(f"  Created:   {key.created_at.strftime('%Y-%m-%d %H:%M UTC')}")
    last = key.last_used_at.strftime("%Y-%m-%d %H:%M UTC") if key.last_used_at else "never"
    print(f"  Last used: {last}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Video Intelligence API key management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Create a new API key")
    p_create.add_argument("--name", required=True, help="Display name for the key owner")
    p_create.add_argument("--plan", choices=PLANS, default="free",
                          help="Subscription plan (default: free)")

    sub.add_parser("list", help="List all API keys")

    p_revoke = sub.add_parser("revoke", help="Revoke an API key")
    p_revoke.add_argument("key", help="The full API key string to revoke")

    p_info = sub.add_parser("info", help="Show details for a specific key")
    p_info.add_argument("key", help="The full API key string")

    args = parser.parse_args()
    {"create": cmd_create, "list": cmd_list, "revoke": cmd_revoke, "info": cmd_info}[args.command](args)


if __name__ == "__main__":
    main()
