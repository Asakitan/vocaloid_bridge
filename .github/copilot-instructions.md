# Project Rules

Use the official MCP Python SDK v1 documentation at https://py.sdk.modelcontextprotocol.io/v1/ and protocol documentation at https://modelcontextprotocol.io/llms-full.txt.

- Use the installed native VSM engine on one STA thread in a private Windows desktop.
- Never activate, send input to, or modify the user's interactive editor.
- No UI, alternate synthesis backend, fake audio, or silent retry fallback is permitted.
- Keep generated projects under workspace/output and separate from user originals.
- Preserve unknown VPR fields and embedded resources when editing files.
- Verify saved projects and synthesized audio from actual files. A VPR is not a synthesized WAV.
- Keep STATUS.md, module-inventory.md, and the session log aligned with observed results.

## Setup Status

- [x] Python MCP package, isolated dependencies, and native host scaffolded.
- [x] Workspace stdio configuration and reproducible setup/smoke tasks created.
- [x] Native host builds and real MCP project lifecycle verification pass.
- [x] Reference repository comparison documented without importing a replacement backend.
- [x] Native WAV synthesis through real MCP, including clean-project reopen and nonzero audio samples.
- [x] User-level VS Code, Claude Code/Desktop, and Codex MCP registration; shared launch configuration verified outside the workspace.
- [x] Expanded 36-tool interface and 119 structured operations; session 08 adds standalone native transport, session-owned freezing and supported VPR extension preservation. Historical full runs and focused deltas are distinguished in STATUS.md.
- [ ] Complete editor-feature coverage fully validated.
