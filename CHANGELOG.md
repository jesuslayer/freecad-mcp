# Changelog

## Unreleased

### Security
- Code filter: refuse private attributes (`random._os`, `collections._sys`
  were a bypass), `FreeCADGui.doCommand*`, `loadFile`, `runCommand`,
  `addModule`, more of `os`'s process API and numpy's `ctypeslib` / `load` /
  `extbuild` / `f2py`.
- RPC: 10 s idle timeout per connection, so silent sockets cannot hold the
  8 concurrency slots and lock out the MCP client.
- Settings file (holds the token) is written atomically and owner-only.

## 0.1.26+hardened.1

Security-hardened fork of upstream freecad-mcp v0.1.26 (`4751f95`).
See [SECURITY.md](SECURITY.md) for the audit behind each change.

### Removed
- `execute_code_headless` tool, `--freecadcmd` option and `headless.py`: it ran
  scripts outside the RPC server, bypassing the auth token.

### Security
- Auth token is mandatory: the addon will not start the RPC server and the MCP
  server exits without one. **Set Auth Token** masks input and can generate a
  random token.
- RPC server requires `Content-Length`, rejects bodies over 2 MiB and caps
  concurrent requests at 8.
- Code filter for `execute_code` / `execute_code_async` (static AST check plus
  restricted runtime builtins), controlled by the `code_filter` setting
  (default on).

### Changed
- Package renamed to `freecad-mcp-hardened`; the command is still `freecad-mcp`.
