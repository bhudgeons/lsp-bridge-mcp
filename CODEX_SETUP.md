# Codex Setup for LSP Bridge (Scala)

Goal: Codex uses the lsp-bridge MCP for fast (~3s) Scala diagnostics instead of `sbt compile`.

## Prereqs
- Metals on PATH (`coursier install metals`, verify `metals --version`; add Coursier bin if needed).
- lsp-bridge-mcp installed (this repo) and Codex CLI installed.

## 1) Add lsp-bridge MCP to Codex

**Option A: Global config (recommended)**
Edit `~/.codex/config.toml`:
```toml
[mcp_servers.lsp-bridge]
command = "python"
args = ["-m", "lsp_bridge"]
```

**Option B: Via CLI**
```
codex mcp add lsp-bridge -- python -m lsp_bridge
```

Restart Codex after adding.

## 2) Diagnostics workflow (Codex)

The lsp-bridge supports **lazy workspace connection** via the `workspace_root` parameter. On the first call, pass the absolute path to your Scala project:

```
trigger_compilation(workspace="metals", workspace_root="/path/to/your/project")
get_diagnostics(workspace="metals")
```

Subsequent calls can omit `workspace_root` since the workspace is already connected:
```
trigger_compilation(workspace="metals")
get_diagnostics(workspace="metals")
```

**Key points:**
- Use `workspace_root` on first call to connect to any Scala project dynamically
- No need to configure static paths in config.toml
- Use `get_hover` for types/docs and `get_definition` for navigation
- Avoid `sbt compile` for errors; use sbt only for tests/run/publish/assembly

## 3) Ensure Bloop before trusting 0 errors
The lsp-bridge will automatically run `sbt bloopInstall` if `.bloop` doesn't exist. However, you can manually ensure it:
```
if [ ! -d .bloop ]; then
  if ! grep -q "sbt-bloop" project/plugins.sbt 2>/dev/null; then
    echo 'addSbtPlugin("ch.epfl.scala" % "sbt-bloop" % "1.5.11")' >> project/plugins.sbt
  fi
  sbt bloopInstall
  sleep 3
fi
```

## 4) Hook note
The existing Claude PostToolUse hook that writes `/tmp/lsp-bridge-notify.txt` is sufficient; the lsp-bridge server watches that file. Codex doesn't need its own hook unless you want Codex to emit notifications separately.

## 5) Quick test
1) Restart Codex.
2) In a Scala project directory, run:
   ```
   trigger_compilation(workspace="metals", workspace_root="/absolute/path/to/project")
   get_diagnostics(workspace="metals")
   ```
3) Use `get_hover`/`get_definition` to explore types and navigate code.  
