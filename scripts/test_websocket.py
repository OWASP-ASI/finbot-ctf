"""
Test WebSocket Events

Pushes synthetic CTF events (activity, challenge_completed, badge_earned,
challenge_progress) to a connected browser session via the debug HTTP
endpoint. Events flow through ws_manager exactly as they would from the
real event processor.

Requires the server running with DEBUG=True and a browser with the CTF
sidecar WebSocket connected.

Audience: Development/testing only.

Usage:
    python scripts/test_websocket.py --namespace ns_user_abc --user-id user_abc
    python scripts/test_websocket.py --namespace ns_user_abc --user-id user_abc --all
"""

import argparse
import sys

try:
    import httpx
except ImportError:
    print("Missing dependency: httpx")
    print("Install:  pip install httpx")
    sys.exit(1)


EVENTS = {
    "1": {
        "label": "activity (agent interaction)",
        "event_type": "activity",
        "data": {
            "event_type": "agent.tool_call",
            "summary": "Test Event triggered by a script",
            "severity": "info",
            "workflow_id": "wf-test-001",
            "agent_name": "onboarding",
        },
    },
    "2": {
        "label": "challenge_completed",
        "event_type": "challenge_completed",
        "data": {
            "challenge_id": "recon-onboarding",
            "challenge_title": "First Contact",
            "points": 100,
        },
    },
    "3": {
        "label": "badge_earned",
        "event_type": "badge_earned",
        "data": {
            "badge_id": "first-blood",
            "badge_title": "First Blood",
            "rarity": "common",
        },
    },
    "4": {
        "label": "challenge_progress",
        "event_type": "challenge_progress",
        "data": {
            "challenge_id": "prompt-leak-onboarding",
            "challenge_title": "Prompt Whisperer",
            "status": "in_progress",
            "attempts": 3,
        },
    },
}


def push_event(
    client: httpx.Client, base_url: str, namespace: str, user_id: str, entry: dict
) -> bool:
    """Push an event to the WebSocket server."""
    payload = {
        "namespace": namespace,
        "user_id": user_id,
        "event_type": entry["event_type"],
        "data": entry["data"],
    }
    resp = client.post(f"{base_url}/ws/test/push", json=payload)
    if resp.status_code == 200:
        result = resp.json()
        if result.get("sent"):
            print(f"  OK  [{entry['label']}] → {result['connections']} connection(s)")
            return True
        print(f"  --  not sent: {result.get('reason')}")
        return False
    if resp.status_code == 404:
        print("  !!  endpoint not found — is DEBUG=True on the server?")
        return False
    print(f"  !!  HTTP {resp.status_code}: {resp.text}")
    return False


def run_interactive(client: httpx.Client, base_url: str, namespace: str, user_id: str):
    """Run the interactive WebSocket test."""
    while True:
        print("\n--- Push event to browser ---")
        for key, evt in EVENTS.items():
            print(f"  [{key}] {evt['label']}")
        print("  [a] send all")
        print("  [q] quit")

        choice = input("\n> ").strip().lower()
        if choice == "q":
            break
        if choice == "a":
            for entry in EVENTS.values():
                push_event(client, base_url, namespace, user_id, entry)
        elif choice in EVENTS:
            push_event(client, base_url, namespace, user_id, EVENTS[choice])
        else:
            print("  !! invalid choice")


def main():
    """Main function to run the WebSocket test."""
    parser = argparse.ArgumentParser(
        description="Push test WS events to a browser session"
    )
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--namespace", required=True, help="Session namespace")
    parser.add_argument("--user-id", required=True, help="Session user ID")
    parser.add_argument("--all", action="store_true", help="Send all events and exit")
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"

    with httpx.Client(timeout=5.0) as client:
        if args.all:
            for entry in EVENTS.values():
                push_event(client, base_url, args.namespace, args.user_id, entry)
        else:
            run_interactive(client, base_url, args.namespace, args.user_id)


if __name__ == "__main__":
    main()
