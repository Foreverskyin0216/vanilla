"""Debug script to test thrift response structure."""

import asyncio
import os
import sys

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()


async def main():
    """Test fetching events and print structure."""
    from src.linepy import login_with_password

    print("Logging in...")
    client = await login_with_password(
        email=os.environ["LINE_EMAIL"],
        password=os.environ["LINE_PASSWORD"],
        device="DESKTOPMAC",
        on_pincode=lambda pin: print(f"Enter PIN: {pin}"),
    )

    print("\n=== Fetching Talk sync events ===")

    # Fetch Talk events
    try:
        # First sync to get revision
        result = await client.base.talk.sync(limit=10)

        print(
            f"First sync result keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}"
        )

        # Check for fullSyncResponse
        full_sync = result.get(2, {})
        revision = full_sync.get(2, 0)
        print(f"Got revision: {revision}")

        if revision:
            print("Waiting 3 seconds for new messages...")
            await asyncio.sleep(3)

            # Sync again with revision
            result = await client.base.talk.sync(limit=10, revision=revision)
            print(
                f"Second sync result keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}"
            )

        print(f"Result type: {type(result)}")
        print(f"Result keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")

        if isinstance(result, dict):
            for key, value in list(result.items())[:5]:
                print(f"\nKey {key} ({type(key).__name__}):")
                if isinstance(value, dict):
                    sub_keys = list(value.keys())[:5]
                    print(f"  Sub-keys: {sub_keys}")
                    # Recursively print structure
                    for sk in sub_keys:
                        sv = value[sk]
                        if isinstance(sv, list):
                            print(f"    {sk}: list of {len(sv)} items")
                            if sv and isinstance(sv[0], dict):
                                print(f"      First item keys: {list(sv[0].keys())[:8]}")
                        elif isinstance(sv, dict):
                            print(f"    {sk}: dict with keys {list(sv.keys())[:5]}")
                        else:
                            print(f"    {sk}: {type(sv).__name__} = {sv}")
                elif isinstance(value, list):
                    print(f"  List length: {len(value)}")
                    if value:
                        print(f"  First item type: {type(value[0])}")
                        if isinstance(value[0], dict):
                            print(f"  First item keys: {list(value[0].keys())[:8]}")
                else:
                    val_str = str(value)[:100] if value else "None"
                    print(f"  Value: {val_str}")
    except Exception as e:
        print(f"Talk sync error: {e}")

    print("\n=== Fetching Square events ===")

    # Fetch Square events
    try:
        result = await client.base.square.fetch_my_events()

        print(f"Result type: {type(result)}")
        print(f"Result keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")

        if isinstance(result, dict):
            for key, value in list(result.items())[:5]:
                print(f"\nKey {key} ({type(key).__name__}):")
                if isinstance(value, dict):
                    print(f"  Sub-keys: {list(value.keys())[:5]}")
                elif isinstance(value, list):
                    print(f"  List length: {len(value)}")
                    if value:
                        print(f"  First item type: {type(value[0])}")
                        if isinstance(value[0], dict):
                            print(f"  First item keys: {list(value[0].keys())}")
                else:
                    print(f"  Value: {value}")
    except Exception as e:
        print(f"Square events error: {e}")

    await client.close()
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
