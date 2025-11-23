#!/usr/bin/env python3
"""Manual test script for LSP bridge."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from lsp_bridge.lsp_client import LSPClient


async def test_metals():
    """Test connecting to Metals."""
    print("🔧 Testing Metals LSP connection...")

    # Load config
    import json
    config_path = Path(__file__).parent / "config.json"
    with open(config_path) as f:
        config = json.load(f)

    server_config = config["servers"][0]
    workspace = server_config["workspace_root"]
    command = server_config["command"]

    client = LSPClient(workspace)

    print(f"📁 Workspace: {workspace}")
    print(f"🚀 Starting Metals with command: {' '.join(command)}...")

    try:
        await client.start(command)
        print("✅ Metals started successfully!")
        print(f"✅ Initialized: {client.initialized}")

        # Open the Scala files so Metals analyzes them
        print("\n📂 Opening Scala files...")
        scala_files = [
            Path(workspace) / "src/main/scala/Main.scala",
            Path(workspace) / "src/main/scala/Calculator.scala",
        ]

        for scala_file in scala_files:
            if scala_file.exists():
                print(f"   Opening {scala_file.name}...")
                with open(scala_file) as f:
                    content = f.read()
                await client.did_open(
                    scala_file.as_uri(),
                    "scala",
                    content
                )

        # Trigger compilation to get diagnostics
        print("\n🔨 Triggering workspace compilation...")
        try:
            compile_result = await client.execute_command("metals.compile-cascade")
            print(f"   Compilation triggered: {compile_result}")
        except Exception as e:
            print(f"   Note: Compile command failed (this is ok): {e}")

        # Wait a bit for diagnostics
        print("\n⏳ Waiting for diagnostics (10 seconds)...")
        await asyncio.sleep(10)

        diagnostics = client.get_diagnostics()
        print(f"\n📊 Diagnostics received for {len(diagnostics)} files")

        total_errors = sum(
            1 for diags in diagnostics.values() for d in diags if d.get("severity") == 1
        )
        total_warnings = sum(
            1 for diags in diagnostics.values() for d in diags if d.get("severity") == 2
        )

        print(f"❌ Errors: {total_errors}")
        print(f"⚠️  Warnings: {total_warnings}")

        if diagnostics:
            print("\n📝 Sample diagnostics:")
            for uri, diags in list(diagnostics.items())[:2]:
                print(f"\n  File: {uri}")
                for diag in diags[:3]:
                    severity = {1: "ERROR", 2: "WARNING", 3: "INFO"}.get(
                        diag.get("severity", 3), "UNKNOWN"
                    )
                    range_info = diag.get("range", {})
                    start = range_info.get("start", {})
                    line = start.get("line", 0) + 1
                    print(f"    [{severity}] Line {line}: {diag.get('message', '')}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()

    finally:
        print("\n🛑 Shutting down...")
        await client.shutdown()
        print("✅ Shutdown complete")


if __name__ == "__main__":
    asyncio.run(test_metals())
