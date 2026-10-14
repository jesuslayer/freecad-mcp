# Security

This is a security-hardened fork of [neka-nat/freecad-mcp](https://github.com/neka-nat/freecad-mcp),
based on upstream **v0.1.26** (commit `4751f95`). It keeps upstream's features
except one, and adds the controls below. Upstream's design, code and MIT license
are credited to its authors; see [LICENSE](LICENSE).

## Threat model

FreeCAD MCP lets an AI agent drive FreeCAD. Two components talk to each other:

- **Addon** (inside FreeCAD): an XML-RPC server on `127.0.0.1:9875`.
- **MCP server** (`freecad-mcp`, started by the MCP client over stdio): forwards
  tool calls to the addon.

The main asset at risk is the user's machine: `execute_code` runs Python inside
FreeCAD with the user's permissions. Attackers considered:

1. **Other local processes** that can reach the loopback port.
2. **Web pages** open in the user's browser (CSRF, DNS rebinding).
3. **Untrusted documents** whose contents reach the model (prompt injection).
4. **The model itself** writing harmful code, by mistake or because it was
   steered.

## Audit of upstream v0.1.26

| Severity | Finding | Status in this fork |
| --- | --- | --- |
| High | Auth token empty by default: any local process could call `execute_code` on `127.0.0.1:9875`. | **Fixed**: token is mandatory on both sides. |
| High | `execute_code_headless` ran scripts in a separate `freecadcmd` process on the MCP host. It bypassed the RPC server (so the token did not apply) and resolved the executable through `PATH`. | **Fixed**: tool removed. |
| Medium | `execute_code` / `execute_code_async` `exec()` arbitrary Python. | **Mitigated**: code filter (below) + manual approval in the client. |
| Medium | Document contents (labels, properties, spreadsheet/text content) are returned to the model unescaped: a crafted `.FCStd` can carry prompt-injection text. | **Documented**: do not open untrusted documents while an agent is connected. |
| Medium | `uvx freecad-mcp` resolves the latest PyPI release; the addon is copied by hand and can drift from the package. | **Mitigated**: install both from the same tag of this fork. |
| Low | No request size limit and one thread per connection (local memory/thread exhaustion). | **Fixed**: 2 MiB body limit, `Content-Length` required, max 8 concurrent requests, 10 s idle timeout per connection. |
| Low | Token stored in plaintext in `freecad_mcp_settings.json` and typed into an unmasked dialog. | **Partly fixed**: dialog masks input and can generate a token. The file stays in FreeCAD's per-user data directory, written atomically and owner-only (`0600`, POSIX). |
| Low | `edit_object` / `create_object` can set any property; opening `.FCStd` files restores FeaturePython proxies. | **Documented**: keep these tools on manual approval. |
| Info | Browser guard (Origin / Content-Type / Host checks) blocks CSRF and DNS rebinding; token compared in constant time; parts library blocks path traversal; no telemetry or outbound network calls. | Kept as is. |

## Controls

### Mandatory auth token

- The addon refuses to start the RPC server without a token
  (`rpc_server.start_rpc_server`).
- The MCP server exits if neither `FREECAD_MCP_TOKEN` nor `--auth-token` is set.
  Prefer the environment variable: command-line arguments are visible in the
  process list.
- **Set Auth Token** masks input; leave it blank to generate
  `secrets.token_urlsafe(32)` and copy it to the clipboard.

### Headless execution removed

`execute_code_headless`, `--freecadcmd` and `freecad_mcp/headless.py` are gone.
Heavy OCCT work can use `execute_code_async`.

### RPC limits

`Content-Length` is required (411) and bodies over 2 MiB are refused (413)
before they are read. At most 8 requests run at once; further connections get
503. A connection that stays silent for 10 s while its request is read is
closed, so idle sockets cannot hold those slots; a slow `execute_code` is not
affected (the timeout covers socket reads and writes only).

### Code filter

While `code_filter` is `true` in `freecad_mcp_settings.json` (the default),
scripts sent to `execute_code` and `execute_code_async` pass two layers
([`code_policy.py`](addon/FreeCADMCP/rpc_server/code_policy.py)):

1. **Static check** before running: imports only from FreeCAD workbenches and
   pure-computation modules (`math`, `numpy`, ...); no `open`, `eval`, `exec`,
   `compile`, `__import__`, `globals`, `vars`...; no dunder names or attributes;
   no private attributes (`_x`, which also covers stdlib aliases such as
   `random._os` and `collections._sys`); no attributes named after system
   modules (e.g. `Draft.os`) or that run code outside the filter
   (`FreeCADGui.doCommand*`, `loadFile`, `runCommand`, `addModule`,
   `numpy.ctypeslib`, `numpy.load`, ...); `getattr`-style
   calls need a literal, non-private name; no string literals containing `__`.
2. **Runtime**: scripts run with restricted builtins whose `__import__`
   refuses system modules (`os`, `subprocess`, `socket`, ...). This layer is a
   denylist because FreeCAD's C++ core imports its own modules (for example
   `PartGui` when `doc.addObject("Part::Box")` runs) through the script's
   builtins.

Refused scripts return the rule and line number without running.

**Limitations.** This is defense in depth, not a sandbox. Python has many
introspection paths, and FreeCAD's own APIs can read and write files
(`Part.read`, `Shape.exportStep`, `doc.saveAs`, ...), and objects such as
`FreeCADGui.getMainWindow()` or `FreeCAD.ParamGet` reach Qt and FreeCAD
preferences. The filter narrows what
can slip through; **manual approval of `execute_code` in your MCP client remains
the real control.** Setting `code_filter` to `false` restores upstream behavior.

## Recommended deployment

- Keep **Remote Connections** off and **Allowed IPs** at `127.0.0.1`.
- Keep **Auto-Start** off; start the RPC server only while you use it.
- Pass the token through `FREECAD_MCP_TOKEN`, never on the command line or in a
  committed file.
- Never auto-approve `execute_code`, `execute_code_async`, `create_object`,
  `edit_object`, `delete_object`, `insert_part_from_library`,
  `reload_document` or `run_fem_analysis`. Read-only tools (`get_view`,
  `get_objects`, `get_object`, `list_documents`, `get_parts_list`,
  `get_rpc_status`, `get_async_status`) are low risk.
- Do not open untrusted `.FCStd` files while an agent is connected; local models
  resist prompt injection less well.
- Install the addon and the MCP server from the same tag of this fork.

## Reporting

Report vulnerabilities specific to this fork through GitHub's private
vulnerability reporting on this repository. Issues that also affect upstream
should be reported to [neka-nat/freecad-mcp](https://github.com/neka-nat/freecad-mcp).
