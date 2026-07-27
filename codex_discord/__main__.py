import argparse
import json
import sys

from .publisher import DeliveryPolicy, publish_notification


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m codex_discord")
    subcommands = parser.add_subparsers(dest="command", required=True)
    publish_parser = subcommands.add_parser("publish")
    publish_parser.add_argument("--endpoint", required=True)
    publish_parser.add_argument("--state-file", required=True)
    publish_parser.add_argument("--mention-user-id")
    publish_parser.add_argument("--enable-milestones", action="store_true")
    publish_parser.add_argument(
        "--max-attempts",
        type=int,
        default=DeliveryPolicy.max_attempts,
    )
    publish_parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=DeliveryPolicy.request_timeout_seconds,
    )
    publish_parser.add_argument(
        "--delivery-timeout-seconds",
        type=float,
        default=DeliveryPolicy.delivery_timeout_seconds,
    )
    args = parser.parse_args()

    try:
        notification = json.load(sys.stdin)
        result = publish_notification(
            notification,
            args.endpoint,
            args.state_file,
            mention_user_id=args.mention_user_id,
            milestones_enabled=args.enable_milestones,
            delivery_policy=DeliveryPolicy(
                max_attempts=args.max_attempts,
                request_timeout_seconds=args.request_timeout_seconds,
                delivery_timeout_seconds=args.delivery_timeout_seconds,
            ),
        )
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        print(f"publish failed: {error}", file=sys.stderr)
        return 1

    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
