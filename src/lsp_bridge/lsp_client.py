"""LSP client implementation for connecting to language servers."""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class LSPClient:
    """Client for communicating with LSP servers via stdio."""

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root).resolve()
        self.process: Optional[asyncio.subprocess.Process] = None
        self.initialized = False
        self.diagnostics: Dict[str, List[Dict[str, Any]]] = {}
        self.request_id = 0
        self.pending_requests: Dict[int, asyncio.Future] = {}
        self.notification_handlers: Dict[str, List[Callable]] = {}
        self._reader_task: Optional[asyncio.Task] = None

    async def start(self, command: List[str]) -> None:
        """Start the LSP server process."""
        logger.info(f"Starting LSP server: {' '.join(command)}")
        self.process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.workspace_root),
        )

        # Start reading responses
        self._reader_task = asyncio.create_task(self._read_responses())

        # Initialize the LSP server
        await self._initialize()

    async def _initialize(self) -> None:
        """Send initialize request to LSP server."""
        init_params = {
            "processId": None,
            "rootUri": self.workspace_root.as_uri(),
            "capabilities": {
                "textDocument": {
                    "publishDiagnostics": {
                        "relatedInformation": True,
                        "tagSupport": {"valueSet": [1, 2]},
                        "codeDescriptionSupport": True,
                    },
                    "hover": {
                        "contentFormat": ["markdown", "plaintext"],
                    },
                }
            },
            "workspaceFolders": [
                {
                    "uri": self.workspace_root.as_uri(),
                    "name": self.workspace_root.name,
                }
            ],
        }

        response = await self._send_request("initialize", init_params)
        logger.info(f"LSP server initialized: {response.get('serverInfo', {})}")

        # Send initialized notification
        await self._send_notification("initialized", {})
        self.initialized = True

        # For Metals: Don't trigger import manually - Metals does it automatically
        # Just wait for Metals to complete its auto-import of Bloop
        logger.info("Waiting for Metals to auto-import build...")
        await asyncio.sleep(10)  # Give Metals time to import build
        logger.info("Metals initialization complete")

    def on_notification(self, method: str, handler: Callable) -> None:
        """Register a handler for a notification method."""
        if method not in self.notification_handlers:
            self.notification_handlers[method] = []
        self.notification_handlers[method].append(handler)

    async def _send_request(self, method: str, params: Any) -> Any:
        """Send a JSON-RPC request and wait for response."""
        if not self.process or not self.process.stdin:
            raise RuntimeError("LSP server not started")

        self.request_id += 1
        request_id = self.request_id

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        # Create future for response
        future = asyncio.Future()
        self.pending_requests[request_id] = future

        # Send request
        content = json.dumps(request)
        message = f"Content-Length: {len(content)}\r\n\r\n{content}"
        self.process.stdin.write(message.encode("utf-8"))
        await self.process.stdin.drain()

        logger.debug(f"Sent request {request_id}: {method}")

        # Wait for response
        return await future

    async def _send_notification(self, method: str, params: Any) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self.process or not self.process.stdin:
            raise RuntimeError("LSP server not started")

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        content = json.dumps(notification)
        message = f"Content-Length: {len(content)}\r\n\r\n{content}"
        self.process.stdin.write(message.encode("utf-8"))
        await self.process.stdin.drain()

        logger.debug(f"Sent notification: {method}")

    async def _read_responses(self) -> None:
        """Read and process responses from the LSP server."""
        if not self.process or not self.process.stdout:
            return

        buffer = b""

        while True:
            try:
                chunk = await self.process.stdout.read(4096)
                if not chunk:
                    break

                buffer += chunk

                while True:
                    # Parse Content-Length header
                    if b"\r\n\r\n" not in buffer:
                        break

                    header_end = buffer.index(b"\r\n\r\n")
                    headers = buffer[:header_end].decode("utf-8")

                    content_length = None
                    for line in headers.split("\r\n"):
                        if line.startswith("Content-Length:"):
                            content_length = int(line.split(":")[1].strip())
                            break

                    if content_length is None:
                        logger.error("No Content-Length header found")
                        buffer = buffer[header_end + 4:]
                        continue

                    # Check if we have the full message
                    message_start = header_end + 4
                    message_end = message_start + content_length

                    if len(buffer) < message_end:
                        break

                    # Extract and parse message
                    message_bytes = buffer[message_start:message_end]
                    buffer = buffer[message_end:]

                    try:
                        message = json.loads(message_bytes.decode("utf-8"))
                        logger.info(f"🔍 Received message: {list(message.keys())}")
                        await self._handle_message(message)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON: {e}")

            except Exception as e:
                logger.error(f"Error reading from LSP server: {e}")
                break

    async def _handle_message(self, message: Dict[str, Any]) -> None:
        """Handle a message from the LSP server."""
        if "id" in message:
            # This is a response to a request
            request_id = message["id"]
            if request_id in self.pending_requests:
                future = self.pending_requests.pop(request_id)
                if "error" in message:
                    future.set_exception(
                        Exception(f"LSP error: {message['error']}")
                    )
                else:
                    future.set_result(message.get("result"))
        elif "method" in message:
            # This is a notification
            method = message["method"]
            params = message.get("params", {})

            logger.info(f"📨 Received notification: {method}")

            # Log important Metals notifications
            if method == "window/logMessage":
                message = params.get("message", "")
                logger.info(f"  Metals: {message}")
            elif method == "window/showMessage":
                message = params.get("message", "")
                logger.info(f"  Metals message: {message}")
            elif method == "metals/status":
                logger.info(f"  Metals status: {params}")

            # Handle diagnostics specially
            if method == "textDocument/publishDiagnostics":
                uri = params.get("uri", "")
                diagnostics = params.get("diagnostics", [])
                self.diagnostics[uri] = diagnostics
                logger.info(
                    f"📊 Updated diagnostics for {uri}: {len(diagnostics)} items"
                )
                if diagnostics:
                    for diag in diagnostics[:3]:  # Log first 3
                        logger.info(f"  - {diag.get('severity')}: {diag.get('message')}")

                # Write diagnostics to temp file for hook integration
                self._write_diagnostics_file()

            # Call registered handlers
            if method in self.notification_handlers:
                for handler in self.notification_handlers[method]:
                    try:
                        await handler(params)
                    except Exception as e:
                        logger.error(f"Error in notification handler: {e}")

    async def did_open(self, uri: str, language_id: str, text: str) -> None:
        """Notify server that a document was opened."""
        await self._send_notification(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": language_id,
                    "version": 1,
                    "text": text,
                }
            },
        )

    async def did_change(self, uri: str, text: str, version: int) -> None:
        """Notify server that a document changed."""
        await self._send_notification(
            "textDocument/didChange",
            {
                "textDocument": {"uri": uri, "version": version},
                "contentChanges": [{"text": text}],
            },
        )

    async def did_save(self, uri: str) -> None:
        """Notify server that a document was saved."""
        await self._send_notification(
            "textDocument/didSave",
            {"textDocument": {"uri": uri}},
        )

    async def hover(self, uri: str, line: int, character: int) -> Optional[Dict[str, Any]]:
        """Get hover information at a position.

        Args:
            uri: The file URI
            line: 0-indexed line number
            character: 0-indexed character position

        Returns:
            Hover response with contents and optional range, or None if no hover info
        """
        try:
            result = await self._send_request(
                "textDocument/hover",
                {
                    "textDocument": {"uri": uri},
                    "position": {"line": line, "character": character},
                },
            )
            return result
        except Exception as e:
            logger.error(f"Hover request failed: {e}")
            return None

    def get_diagnostics(self, uri: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """Get diagnostics for a file or all files."""
        if uri:
            return {uri: self.diagnostics.get(uri, [])}
        return self.diagnostics.copy()

    def _write_diagnostics_file(self) -> None:
        """Write current diagnostics to workspace .lsp-bridge directory."""
        try:
            # Count errors and warnings
            errors = []
            warnings = []
            for uri, diags in self.diagnostics.items():
                file_path = uri.replace("file://", "")
                file_name = Path(file_path).name
                for diag in diags:
                    severity = diag.get("severity", 3)
                    line = diag.get("range", {}).get("start", {}).get("line", 0) + 1
                    msg = diag.get("message", "")
                    entry = {"file": file_name, "line": line, "message": msg}
                    if severity == 1:
                        errors.append(entry)
                    elif severity == 2:
                        warnings.append(entry)

            output = {
                "error_count": len(errors),
                "warning_count": len(warnings),
                "errors": errors[:5],  # Limit to first 5
                "warnings": warnings[:3],  # Limit to first 3
            }

            # Write to workspace .lsp-bridge directory
            lsp_dir = self.workspace_root / ".lsp-bridge"
            lsp_dir.mkdir(exist_ok=True)
            with open(lsp_dir / "diagnostics.json", "w") as f:
                json.dump(output, f)

            # Also write to /tmp for backwards compatibility
            with open("/tmp/lsp-bridge-diagnostics.json", "w") as f:
                json.dump(output, f)
        except Exception as e:
            logger.error(f"Failed to write diagnostics file: {e}")

    async def execute_command(self, command: str, arguments: List[Any] = None) -> Any:
        """Execute a workspace command (e.g., trigger compilation)."""
        return await self._send_request(
            "workspace/executeCommand",
            {"command": command, "arguments": arguments or []},
        )

    async def shutdown(self) -> None:
        """Shutdown the LSP server."""
        if self.initialized:
            await self._send_request("shutdown", None)
            await self._send_notification("exit", None)

        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        if self.process:
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
