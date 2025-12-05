# Scala Demo Project

A sample Scala project for demonstrating lsp-bridge-mcp features with Claude Code.

## Project Structure

```
scalademo/
├── src/main/scala/
│   ├── App.scala                      # Main application
│   ├── models/User.scala              # User case class with companion
│   └── services/
│       ├── UserService.scala          # User CRUD operations
│       └── EmailValidator.scala       # Email validation with ValidationResult
├── build.sbt
└── README.md
```

## Setup

1. **Generate Bloop configuration** (required for Metals):
   ```bash
   cd scalademo
   sbt bloopInstall
   ```

2. **Start Claude Code** in the scalademo directory

3. **Verify LSP is working**:
   ```
   list_workspaces
   ```

## Demo Prompts

These prompts demonstrate lsp-bridge-mcp features through natural coding tasks. Claude is configured to use LSP tools proactively.

### Demo 1: Auto-Diagnostics
```
Add a method to UserService that finds all users whose email ends with a specific domain, like "@example.com"
```
**What to watch for:**
- Claude reads UserService.scala
- Claude adds the method
- Diagnostics check happens automatically (~3 seconds)
- Claude confirms 0 errors

### Demo 2: Hover for Inferred Return Type
```
In App.scala, add code to call service.analyzeByDomain and print each domain with its user count.
```
**What to watch for:**
- Claude reads App.scala, sees `service` is a UserService
- Claude needs to know what `analyzeByDomain` returns to iterate over it
- The method has NO explicit return type in the source code - Scala infers it
- Claude uses `get_hover` on `analyzeByDomain` to discover: `Iterable[(String, Int, List[String])]`
- Claude CANNOT determine this just by reading UserService.scala - only the compiler knows
- Claude then writes correct code to destructure the tuples and print them

### Demo 3: Go to Definition
```
The User.create method in App.scala rejects emails without an "@" sign. I want it to also reject emails without a dot after the @. Update the validation.
```
**What to watch for:**
- Claude reads App.scala and sees the `User.create` call
- Claude uses `get_definition` to jump directly to the validation logic in User.scala
- No searching or grepping - goes straight to the right file and line
- Claude updates the validation logic and confirms it compiles

### Demo 4: Refactoring
```
Rename the greeting method in User to welcomeMessage. Make sure nothing breaks.
```
**What to watch for:**
- Claude makes the change in User.scala
- LSP immediately flags the error in App.scala (call site)
- Claude fixes the call site
- Confirms 0 errors

## Key Behaviors to Highlight

1. **Proactive hover usage**: Claude uses `get_hover` to check types BEFORE reading source files
2. **Direct navigation**: Claude uses `get_definition` instead of searching/grepping
3. **Instant feedback**: Compilation errors appear in ~3 seconds, not 30+
4. **Confident iteration**: Claude edits, checks, fixes quickly

## What Makes This Impressive

- **Speed**: LSP gives ~3 second compilation feedback vs 30+ seconds for `sbt compile`
- **Proactive**: Claude reaches for LSP tools first, not as a fallback
- **Rich Information**: Hover shows full type signatures AND documentation
- **Navigation**: Go-to-definition works for project code AND library code
- **No Context Switching**: Claude stays in flow, doesn't shell out to slow build tools

## Tips for Recording

- Restart Claude Code before recording to ensure fresh session with latest instructions
- Demo 2 (hover for inferred type) and Demo 3 (go-to-definition) best showcase proactive LSP usage
- Demo 4 shows LSP catching errors across files during refactoring
- If Claude reads a file instead of using hover, the task still works - but you can point out "with LSP tools, Claude could have just hovered to get the type"
