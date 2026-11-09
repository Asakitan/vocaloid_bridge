# MCP-owned VOCALOID runtime

The caller does not need to open the interactive editor. `project_create`,
`project_open` and other bootstrap requests start a private native process on
demand. All project operations continue through the same MCP server.

`vocaloid_runtime` exposes:

| Operation | Behavior |
| --- | --- |
| `status` | Report whether the owned process is running; a cold status does not start it. |
| `start` | Start and handshake with the private native process, or report the running instance. |
| `stop` | Stop only this server's owned process; active projects require explicit `discard_sessions=true`. |
| `restart` | Apply the same active-project protection, then start a new native generation. |

Results include `running`, `generation`, `managed_by_mcp`, and the MCP version.
Running results also contain the native PID, private desktop and session count.
The first native handshake binds the process's unique cache namespace. Process
shutdown releases the host snapshot, private temporary directory and confirmed
ended cache namespace. MCP Python temporary files use `.runtime/mcp-temp`; native
children use separate `.runtime/tmp/<desktop>` directories under the E-drive workspace.

## Recovery contract

A process proven exited before dispatch can be replaced for a new/open project or
other bootstrap request. References to its old projects and objects expire.
The Agent can reopen the last saved VPR through MCP; an unsaved project is not
represented as recovered.

A request whose connection failed after dispatch is never automatically replayed.
The MCP reports an unknown outcome, releases the broken native instance and accepts
an explicit fresh start/create/open. Local JSON encoding errors do not tear down a
healthy process. A native operation error returned over a healthy connection is
not treated as a transport failure.

This manages **VOCALOID's private native runtime**, not the Codex application or
the MCP client's own connection to this server. It never activates the user's
editor or runs a second UI-based backend.

## Focused evidence

`runtime.lifecycle_35` covers cold automatic start, native project editing and
save/reopen, active-session restart protection, explicit stop/start/restart,
confirmed process-death recovery and cache cleanup. `runtime.no_replay_35` covers
a lost response, no automatic replay, expired handle rejection and a fresh request.
The tests use a real isolated native host. No native rebuild or broad suite was
needed for this Python-only change.
