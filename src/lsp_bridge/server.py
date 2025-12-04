"""MCP server that bridges to LSP servers."""

import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    GetPromptResult,
    Prompt,
)

from .lsp_client import LSPClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("/tmp/lsp-bridge-mcp.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


LSP_BRIDGE_INSTRUCTIONS = """
NEVER run `sbt compile` or `sbt test:compile` to check for Scala compilation errors. ALWAYS use LSP:

1. list_workspaces
2. trigger_compilation workspace="metals"
3. get_diagnostics workspace="metals"

This applies EVERY time you need to check compilation - after edits, when fixing errors, when verifying changes.
Use sbt ONLY for: running tests (sbt test), running the app (sbt run), or packaging (sbt assembly).

For type information and documentation, use get_hover:
  get_hover(workspace="metals", file_path="/path/to/File.scala", line=10, character=15)

This returns method signatures, case class fields, scaladoc, and type information instantly.
"""


class LSPBridgeServer:
    """MCP server that connects to LSP servers."""

    def __init__(self):
        self.server = Server("lsp-bridge", instructions=LSP_BRIDGE_INSTRUCTIONS.strip())
        self.lsp_clients: Dict[str, LSPClient] = {}
        self.config: Dict[str, Any] = {}
        self.opened_files: Dict[str, set] = {}  # workspace -> set of opened file URIs
        self.file_versions: Dict[str, int] = {}  # uri -> version for didChange
        self._notify_watcher_task: Optional[asyncio.Task] = None
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Set up MCP server handlers."""

        @self.server.list_resources()
        async def list_resources() -> List[Resource]:
            """List available diagnostic resources."""
            resources = []

            for workspace, client in self.lsp_clients.items():
                # Add resource for all diagnostics
                resources.append(
                    Resource(
                        uri=f"lsp://{workspace}/diagnostics/all",
                        name=f"All Diagnostics ({workspace})",
                        mimeType="application/json",
                        description=f"All compilation errors and warnings for {workspace}",
                    )
                )

                # Add resources for each file with diagnostics
                diagnostics = client.get_diagnostics()
                for file_uri, diags in diagnostics.items():
                    if diags:
                        file_path = file_uri.replace("file://", "")
                        resources.append(
                            Resource(
                                uri=f"lsp://{workspace}/diagnostics/{file_path}",
                                name=f"Diagnostics: {Path(file_path).name}",
                                mimeType="application/json",
                                description=f"{len(diags)} diagnostic(s) in {file_path}",
                            )
                        )

            return resources

        @self.server.read_resource()
        async def read_resource(uri: str) -> str:
            """Read diagnostic resource content."""
            # Convert AnyUrl to string (MCP framework may pass Pydantic AnyUrl)
            uri = str(uri)
            logger.info(f"Reading resource: {uri}")

            # Parse URI: lsp://workspace/diagnostics/[all|file_path]
            if not uri.startswith("lsp://"):
                raise ValueError(f"Invalid URI scheme: {uri}")

            parts = uri.replace("lsp://", "").split("/diagnostics/", 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid URI format: {uri}")

            workspace, path = parts

            if workspace not in self.lsp_clients:
                raise ValueError(f"Unknown workspace: {workspace}")

            client = self.lsp_clients[workspace]

            if path == "all":
                # Return all diagnostics
                diagnostics = client.get_diagnostics()
                return json.dumps(self._format_diagnostics(diagnostics), indent=2)
            else:
                # Return diagnostics for specific file
                file_uri = f"file://{path}"
                diagnostics = client.get_diagnostics(file_uri)
                return json.dumps(self._format_diagnostics(diagnostics), indent=2)

        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available LSP tools."""
            return [
                Tool(
                    name="get_diagnostics",
                    description="Get compilation errors, warnings, and diagnostics from the LSP server",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "workspace": {
                                "type": "string",
                                "description": "Workspace name (e.g., 'metals')",
                            },
                            "file_path": {
                                "type": "string",
                                "description": "Optional: specific file path to get diagnostics for",
                            },
                        },
                        "required": ["workspace"],
                    },
                ),
                Tool(
                    name="trigger_compilation",
                    description="Trigger compilation in the LSP server (if supported)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "workspace": {
                                "type": "string",
                                "description": "Workspace name (e.g., 'metals')",
                            },
                        },
                        "required": ["workspace"],
                    },
                ),
                Tool(
                    name="list_workspaces",
                    description="List all connected LSP server workspaces",
                    inputSchema={"type": "object", "properties": {}},
                ),
                Tool(
                    name="get_status",
                    description="Get the status of LSP servers and compilation state",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "workspace": {
                                "type": "string",
                                "description": "Optional: specific workspace to check",
                            },
                        },
                    },
                ),
                Tool(
                    name="get_hover",
                    description="Get type information, documentation, and signatures for a symbol at a specific position. Use this to quickly look up method signatures, case class fields, type definitions, etc. without searching through code.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "workspace": {
                                "type": "string",
                                "description": "Workspace name (e.g., 'metals')",
                            },
                            "file_path": {
                                "type": "string",
                                "description": "Absolute path to the file",
                            },
                            "line": {
                                "type": "integer",
                                "description": "Line number (1-indexed, as shown in editors)",
                            },
                            "character": {
                                "type": "integer",
                                "description": "Character/column position (0-indexed)",
                            },
                        },
                        "required": ["workspace", "file_path", "line", "character"],
                    },
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Any) -> List[TextContent]:
            """Handle tool calls."""
            logger.info(f"Tool called: {name} with args: {arguments}")

            if name == "list_workspaces":
                # Auto-detect on first call if no workspaces
                if not self.lsp_clients:
                    logger.info("No workspaces connected, attempting auto-detection...")
                    await self.auto_detect_workspace()

                logger.info(f"Current lsp_clients: {self.lsp_clients}")
                workspaces = list(self.lsp_clients.keys())
                logger.info(f"Returning workspaces: {workspaces}")
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "workspaces": workspaces,
                                "count": len(workspaces),
                            },
                            indent=2,
                        ),
                    )
                ]

            elif name == "get_diagnostics":
                workspace = arguments.get("workspace")
                file_path = arguments.get("file_path")

                # Auto-detect on first call if no workspaces
                if not self.lsp_clients:
                    logger.info("No workspaces connected, attempting auto-detection...")
                    await self.auto_detect_workspace()

                if workspace not in self.lsp_clients:
                    return [
                        TextContent(
                            type="text",
                            text=f"Error: Unknown workspace '{workspace}'. Available: {list(self.lsp_clients.keys())}",
                        )
                    ]

                client = self.lsp_clients[workspace]

                # Open all Scala files in workspace if not already opened
                await self._ensure_files_opened(client, workspace)

                # Trigger Metals to compile the workspace
                try:
                    if workspace == "metals":
                        logger.info("Triggering Metals compilation...")
                        await client.execute_command("metals.compile-cascade")
                        logger.info("Compilation triggered, waiting for diagnostics...")
                except Exception as e:
                    logger.warning(f"Failed to trigger compilation: {e}")

                # Wait longer for Metals to analyze files (especially on first call)
                # Metals needs time to connect to Bloop and analyze files
                await asyncio.sleep(8)

                if file_path:
                    file_uri = Path(file_path).resolve().as_uri()
                    diagnostics = client.get_diagnostics(file_uri)
                else:
                    diagnostics = client.get_diagnostics()

                formatted = self._format_diagnostics(diagnostics)

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(formatted, indent=2),
                    )
                ]

            elif name == "trigger_compilation":
                workspace = arguments.get("workspace")

                if workspace not in self.lsp_clients:
                    return [
                        TextContent(
                            type="text",
                            text=f"Error: Unknown workspace '{workspace}'",
                        )
                    ]

                client = self.lsp_clients[workspace]

                try:
                    # Metals-specific: trigger compilation
                    if workspace == "metals":
                        result = await client.execute_command("metals.compile-cascade")
                        return [
                            TextContent(
                                type="text",
                                text=f"Compilation triggered. Result: {json.dumps(result, indent=2)}",
                            )
                        ]
                    else:
                        return [
                            TextContent(
                                type="text",
                                text=f"Compilation trigger not yet implemented for {workspace}",
                            )
                        ]
                except Exception as e:
                    return [
                        TextContent(
                            type="text",
                            text=f"Error triggering compilation: {str(e)}",
                        )
                    ]

            elif name == "get_status":
                workspace = arguments.get("workspace")

                if workspace:
                    if workspace not in self.lsp_clients:
                        return [
                            TextContent(
                                type="text",
                                text=f"Error: Unknown workspace '{workspace}'",
                            )
                        ]

                    client = self.lsp_clients[workspace]
                    diagnostics = client.get_diagnostics()

                    error_count = sum(
                        1
                        for diags in diagnostics.values()
                        for d in diags
                        if d.get("severity") == 1
                    )
                    warning_count = sum(
                        1
                        for diags in diagnostics.values()
                        for d in diags
                        if d.get("severity") == 2
                    )

                    status = {
                        "workspace": workspace,
                        "initialized": client.initialized,
                        "files_with_diagnostics": len(diagnostics),
                        "total_errors": error_count,
                        "total_warnings": warning_count,
                    }
                else:
                    # All workspaces
                    status = {}
                    for ws_name, client in self.lsp_clients.items():
                        diagnostics = client.get_diagnostics()
                        error_count = sum(
                            1
                            for diags in diagnostics.values()
                            for d in diags
                            if d.get("severity") == 1
                        )
                        warning_count = sum(
                            1
                            for diags in diagnostics.values()
                            for d in diags
                            if d.get("severity") == 2
                        )

                        status[ws_name] = {
                            "initialized": client.initialized,
                            "files_with_diagnostics": len(diagnostics),
                            "total_errors": error_count,
                            "total_warnings": warning_count,
                        }

                return [
                    TextContent(
                        type="text",
                        text=json.dumps(status, indent=2),
                    )
                ]

            elif name == "get_hover":
                workspace = arguments.get("workspace")
                file_path = arguments.get("file_path")
                line = arguments.get("line")
                character = arguments.get("character")

                if not all([workspace, file_path, line is not None, character is not None]):
                    return [
                        TextContent(
                            type="text",
                            text="Error: workspace, file_path, line, and character are required",
                        )
                    ]

                # Auto-detect on first call if no workspaces
                if not self.lsp_clients:
                    logger.info("No workspaces connected, attempting auto-detection...")
                    await self.auto_detect_workspace()

                if workspace not in self.lsp_clients:
                    return [
                        TextContent(
                            type="text",
                            text=f"Error: Unknown workspace '{workspace}'. Available: {list(self.lsp_clients.keys())}",
                        )
                    ]

                client = self.lsp_clients[workspace]

                # Ensure file is opened in LSP
                path = Path(file_path).resolve()
                uri = path.as_uri()

                if workspace not in self.opened_files:
                    self.opened_files[workspace] = set()

                if uri not in self.opened_files[workspace]:
                    try:
                        content = path.read_text()
                        await client.did_open(uri, "scala", content)
                        self.opened_files[workspace].add(uri)
                        logger.info(f"Opened file for hover: {path.name}")
                        # Give Metals a moment to analyze the file
                        await asyncio.sleep(2)
                    except Exception as e:
                        return [
                            TextContent(
                                type="text",
                                text=f"Error opening file: {e}",
                            )
                        ]

                # Convert 1-indexed line to 0-indexed for LSP
                lsp_line = line - 1

                # Get hover info
                hover_result = await client.hover(uri, lsp_line, character)

                if not hover_result:
                    return [
                        TextContent(
                            type="text",
                            text=f"No hover information at {path.name}:{line}:{character}",
                        )
                    ]

                # Format the hover result
                formatted = self._format_hover(hover_result, path.name, line, character)

                return [
                    TextContent(
                        type="text",
                        text=formatted,
                    )
                ]

            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        @self.server.list_prompts()
        async def list_prompts() -> List[Prompt]:
            """List available prompts."""
            return [
                Prompt(
                    name="analyze_diagnostics",
                    description="Analyze and explain compilation diagnostics",
                    arguments=[
                        {
                            "name": "workspace",
                            "description": "Workspace name",
                            "required": True,
                        }
                    ],
                )
            ]

        @self.server.get_prompt()
        async def get_prompt(name: str, arguments: Dict[str, str]) -> GetPromptResult:
            """Get a prompt with diagnostics."""
            if name == "analyze_diagnostics":
                workspace = arguments.get("workspace", "metals")

                if workspace not in self.lsp_clients:
                    return GetPromptResult(
                        messages=[
                            {
                                "role": "user",
                                "content": {
                                    "type": "text",
                                    "text": f"Error: Unknown workspace '{workspace}'",
                                },
                            }
                        ]
                    )

                client = self.lsp_clients[workspace]
                diagnostics = client.get_diagnostics()
                formatted = self._format_diagnostics(diagnostics)

                prompt_text = f"""Analyze the following compilation diagnostics and provide:
1. A summary of all errors and warnings
2. Root cause analysis
3. Suggested fixes for each issue
4. Priority order for fixing issues

Diagnostics:
{json.dumps(formatted, indent=2)}
"""

                return GetPromptResult(
                    messages=[
                        {
                            "role": "user",
                            "content": {"type": "text", "text": prompt_text},
                        }
                    ]
                )

            raise ValueError(f"Unknown prompt: {name}")

    async def _ensure_files_opened(self, client: LSPClient, workspace: str) -> None:
        """Ensure all Scala files in the workspace are opened in the LSP server."""
        if workspace not in self.opened_files:
            self.opened_files[workspace] = set()

        # Only open files if we haven't opened them recently
        # (within the last 30 seconds to avoid re-opening constantly)
        import time
        if hasattr(client, '_last_files_opened'):
            if time.time() - client._last_files_opened < 30:
                logger.info("Files recently opened, skipping re-open")
                return

        # Find all Scala files in the workspace
        workspace_path = client.workspace_root
        scala_files = list(workspace_path.glob("src/**/*.scala"))

        for scala_file in scala_files:
            file_uri = scala_file.resolve().as_uri()

            # Skip if already opened
            if file_uri in self.opened_files[workspace]:
                continue

            try:
                # Read file content
                with open(scala_file, 'r') as f:
                    content = f.read()

                # Open the file in Metals
                await client.did_open(file_uri, "scala", content)
                self.opened_files[workspace].add(file_uri)
                logger.info(f"Opened file in Metals: {scala_file.name}")
            except Exception as e:
                logger.error(f"Failed to open {scala_file}: {e}")

        # Mark files as opened
        import time
        client._last_files_opened = time.time()

    def _format_hover(
        self, hover_result: Dict[str, Any], file_name: str, line: int, character: int
    ) -> str:
        """Format hover result for readable output."""
        contents = hover_result.get("contents", {})

        # Handle different content formats
        if isinstance(contents, str):
            text = contents
        elif isinstance(contents, dict):
            # MarkupContent format
            text = contents.get("value", str(contents))
        elif isinstance(contents, list):
            # Array of MarkedString
            parts = []
            for item in contents:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.append(item.get("value", str(item)))
            text = "\n\n".join(parts)
        else:
            text = str(contents)

        # Add location context
        result = f"**Hover info at {file_name}:{line}:{character}**\n\n{text}"

        # Add range info if available
        if "range" in hover_result:
            range_info = hover_result["range"]
            start = range_info.get("start", {})
            end = range_info.get("end", {})
            result += f"\n\n_Symbol spans: {start.get('line', 0) + 1}:{start.get('character', 0)} - {end.get('line', 0) + 1}:{end.get('character', 0)}_"

        return result

    def _format_diagnostics(
        self, diagnostics: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """Format diagnostics for readable output."""
        formatted = {
            "summary": {
                "total_files": len(diagnostics),
                "total_diagnostics": sum(len(diags) for diags in diagnostics.values()),
                "errors": 0,
                "warnings": 0,
                "info": 0,
            },
            "by_file": {},
        }

        for file_uri, diags in diagnostics.items():
            if not diags:
                continue

            file_path = file_uri.replace("file://", "")
            formatted_diags = []

            for diag in diags:
                severity = diag.get("severity", 3)
                severity_name = {1: "ERROR", 2: "WARNING", 3: "INFO", 4: "HINT"}.get(
                    severity, "UNKNOWN"
                )

                if severity == 1:
                    formatted["summary"]["errors"] += 1
                elif severity == 2:
                    formatted["summary"]["warnings"] += 1
                else:
                    formatted["summary"]["info"] += 1

                range_info = diag.get("range", {})
                start = range_info.get("start", {})
                line = start.get("line", 0) + 1  # LSP is 0-indexed
                character = start.get("character", 0)

                formatted_diags.append(
                    {
                        "severity": severity_name,
                        "line": line,
                        "character": character,
                        "message": diag.get("message", ""),
                        "source": diag.get("source", ""),
                        "code": diag.get("code", ""),
                    }
                )

            formatted["by_file"][file_path] = formatted_diags

        return formatted

    async def start_lsp_client(
        self, workspace_name: str, workspace_root: str, command: List[str]
    ) -> None:
        """Start an LSP client for a workspace."""
        logger.info(
            f"Starting LSP client for {workspace_name} at {workspace_root}"
        )

        # For Metals: Ensure Bloop is configured BEFORE starting Metals
        if workspace_name == "metals":
            workspace_path = Path(workspace_root)
            bloop_dir = workspace_path / ".bloop"
            if not bloop_dir.exists():
                logger.info("No .bloop directory found, configuring Bloop first...")

                # Ensure sbt-bloop plugin is configured
                plugins_file = workspace_path / "project" / "plugins.sbt"
                plugins_file.parent.mkdir(exist_ok=True)
                if not plugins_file.exists() or "sbt-bloop" not in plugins_file.read_text():
                    with open(plugins_file, "a") as f:
                        f.write('\naddSbtPlugin("ch.epfl.scala" % "sbt-bloop" % "1.5.11")\n')
                    logger.info("Added sbt-bloop plugin")

                # Run sbt bloopInstall with retries for JVM crashes
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        logger.info(f"Running sbt bloopInstall (attempt {attempt + 1}/{max_retries})...")
                        result = subprocess.run(
                            ["sbt", "bloopInstall"],
                            cwd=workspace_root,
                            capture_output=True,
                            text=True,
                            timeout=60
                        )
                        if result.returncode == 0 or bloop_dir.exists():
                            logger.info("Bloop configured successfully")
                            break
                        elif "SIGSEGV" in result.stderr or result.returncode == 134:
                            logger.warning(f"JVM crash detected, retrying...")
                            await asyncio.sleep(2)
                    except Exception as e:
                        logger.warning(f"Failed to run sbt bloopInstall: {e}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2)
            else:
                logger.info(".bloop directory exists, skipping bloopInstall")

        client = LSPClient(workspace_root)
        await client.start(command)

        self.lsp_clients[workspace_name] = client
        logger.info(f"LSP client {workspace_name} started successfully")

    async def auto_detect_workspace(self) -> None:
        """Auto-detect workspace and start appropriate LSP servers."""
        import os

        # Check multiple locations for Scala projects
        check_paths = []

        # 1. Environment variable
        if os.environ.get("LSP_WORKSPACE"):
            check_paths.append(Path(os.environ["LSP_WORKSPACE"]).resolve())

        # 2. Current working directory
        check_paths.append(Path(os.getcwd()).resolve())

        # 3. Common project locations
        # Check common development directories
        home = Path.home()
        common_locations = [
            home / "work",
            home / "projects",
            home / "src",
            home / "code",
            home,
        ]

        for loc in common_locations:
            if loc.exists():
                check_paths.append(loc.resolve())

        logger.info(f"Auto-detecting workspace, checking paths: {check_paths}")

        # Find and start all Scala projects
        scala_projects_found = []

        for workspace_path in check_paths:
            if not workspace_path.exists():
                continue

            # Check direct path
            if (workspace_path / "build.sbt").exists() or (workspace_path / "build.sc").exists():
                if str(workspace_path) not in scala_projects_found:
                    scala_projects_found.append(str(workspace_path))
                    logger.info(f"Found Scala project at {workspace_path}")

                    # Start Metals for this workspace
                    await self.start_lsp_client(
                        "metals",
                        str(workspace_path),
                        ["/usr/local/bin/metals-vim"]
                    )
                    logger.info(f"Started Metals for {workspace_path}")
                    break  # Start only the first found project

            # Also check subdirectories (one level deep)
            if workspace_path.is_dir():
                for subdir in workspace_path.iterdir():
                    if subdir.is_dir() and not subdir.name.startswith('.'):
                        if (subdir / "build.sbt").exists() or (subdir / "build.sc").exists():
                            if str(subdir) not in scala_projects_found:
                                scala_projects_found.append(str(subdir))
                                logger.info(f"Found Scala project at {subdir}")

                                # Start Metals for this workspace
                                await self.start_lsp_client(
                                    "metals",
                                    str(subdir),
                                    ["/usr/local/bin/metals-vim"]
                                )
                                logger.info(f"Started Metals for {subdir}")
                                break  # Start only the first found project

                if scala_projects_found:
                    break

        if not scala_projects_found:
            logger.info("No Scala projects found during auto-detection")

    async def load_config(self, config_path: str) -> None:
        """Load configuration from file."""
        config_file = Path(config_path)
        if not config_file.exists():
            logger.warning(f"Config file not found: {config_path}")
            return

        with open(config_file) as f:
            self.config = json.load(f)

        logger.info(f"Loaded config: {self.config}")

        # Start configured LSP servers
        for server_config in self.config.get("servers", []):
            workspace_name = server_config["name"]
            workspace_root = server_config["workspace_root"]
            command = server_config["command"]

            await self.start_lsp_client(workspace_name, workspace_root, command)

    async def _watch_notify_file(self) -> None:
        """Watch for file change notifications from hooks."""
        notify_file = Path("/tmp/lsp-bridge-notify.txt")
        last_mtime = 0.0

        while True:
            try:
                if notify_file.exists():
                    mtime = notify_file.stat().st_mtime
                    if mtime > last_mtime:
                        last_mtime = mtime
                        file_path = notify_file.read_text().strip()
                        if file_path and file_path.endswith(".scala"):
                            logger.info(f"Hook notification for: {file_path}")
                            await self._notify_file_changed(file_path)
                await asyncio.sleep(0.5)  # Check every 500ms
            except Exception as e:
                logger.error(f"Error in notify watcher: {e}")
                await asyncio.sleep(1)

    async def _notify_file_changed(self, file_path: str) -> None:
        """Send didChange notification to Metals for a file."""
        try:
            path = Path(file_path).resolve()
            uri = path.as_uri()

            # Auto-detect workspace if none connected
            if not self.lsp_clients:
                logger.info("No workspaces connected, auto-detecting for file change...")
                await self.auto_detect_workspace()

            # Find the appropriate client
            for workspace, client in self.lsp_clients.items():
                if str(path).startswith(str(client.workspace_root)):
                    # Read the file content
                    content = path.read_text()

                    # Increment version
                    self.file_versions[uri] = self.file_versions.get(uri, 0) + 1
                    version = self.file_versions[uri]

                    # Send didChange
                    await client.did_change(uri, content, version)
                    logger.info(f"Sent didChange for {path.name} (v{version})")

                    # Trigger compilation
                    if workspace == "metals":
                        await client.execute_command("metals.compile-cascade")
                        logger.info("Triggered compilation after file change")
                    break
            else:
                logger.warning(f"No workspace found for {file_path}")
        except Exception as e:
            logger.error(f"Failed to notify file change: {e}")

    async def run(self, config_path: Optional[str] = None) -> None:
        """Run the MCP server."""
        if config_path:
            await self.load_config(config_path)

        # Start the notify file watcher
        self._notify_watcher_task = asyncio.create_task(self._watch_notify_file())

        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )

    async def shutdown(self) -> None:
        """Shutdown all LSP clients."""
        for client in self.lsp_clients.values():
            await client.shutdown()


def main():
    """Main entry point."""
    import os

    # Check for config path from args or auto-detect
    config_path = sys.argv[1] if len(sys.argv) > 1 else None

    # If no config, try to auto-detect Scala project
    if not config_path:
        workspace = os.environ.get("LSP_WORKSPACE") or os.getcwd()
        workspace_path = Path(workspace).resolve()

        # Check if this is a Scala/sbt project
        if (workspace_path / "build.sbt").exists() or (workspace_path / "build.sc").exists():
            logger.info(f"Auto-detected Scala project at {workspace_path}")

            # Create temporary config
            import tempfile
            import json

            temp_config = {
                "servers": [
                    {
                        "name": "metals",
                        "workspace_root": str(workspace_path),
                        "command": ["/usr/local/bin/metals-vim"]
                    }
                ]
            }

            # Write to temp file
            fd, config_path = tempfile.mkstemp(suffix=".json")
            with os.fdopen(fd, 'w') as f:
                json.dump(temp_config, f)

            logger.info(f"Created auto-config for {workspace_path}")

    server = LSPBridgeServer()

    try:
        asyncio.run(server.run(config_path))
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        asyncio.run(server.shutdown())


if __name__ == "__main__":
    main()
