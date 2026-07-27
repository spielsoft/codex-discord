import argparse
import json
import sys

from .publisher import DeliveryPolicy, publish_notification


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m codex_discord")
    subcommands = parser.add_subparsers(dest="command", required=True)
    operation_parsers = []
    for operation in ("publish", "milestone"):
        operation_parser = subcommands.add_parser(operation)
        operation_parser.add_argument("--endpoint", required=True)
        operation_parser.add_argument("--state-file", required=True)
        operation_parser.add_argument("--mention-user-id")
        operation_parser.add_argument(
            "--max-attempts",
            type=int,
            default=DeliveryPolicy.max_attempts,
        )
        operation_parser.add_argument(
            "--request-timeout-seconds",
            type=float,
            default=DeliveryPolicy.request_timeout_seconds,
        )
        operation_parser.add_argument(
            "--delivery-timeout-seconds",
            type=float,
            default=DeliveryPolicy.delivery_timeout_seconds,
        )
        operation_parsers.append(operation_parser)
    operation_parsers[0].add_argument(
        "--enable-milestones",
        action="store_true",
    )
    operation_parsers[1].add_argument("--enable", action="store_true")
    args = parser.parse_args()

    try:
        notification = json.load(sys.stdin)
        milestones_enabled = (
            args.enable_milestones
            if args.command == "publish"
            else args.enable
        )
        if args.command == "milestone":
            if not isinstance(notification, dict):
                raise TypeError("notification must be a JSON object")
            notification = {**notification, "status": "milestone"}
        result = publish_notification(
            notification,
            args.endpoint,
            args.state_file,
            mention_user_id=args.mention_user_id,
            milestones_enabled=milestones_enabled,
            delivery_policy=DeliveryPolicy(
                max_attempts=args.max_attempts,
                request_timeout_seconds=args.request_timeout_seconds,
                delivery_timeout_seconds=args.delivery_timeout_seconds,
            ),
        )
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        print(f"{args.command} failed: {error}", file=sys.stderr)
        return 1

    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
