# Project Rules

Current host targets .NET 10 and selects installed VOCALOID6/7 through
`vocaloid_bridge/install.py`. Build through `tools/setup.ps1`; products have
separate output/intermediate paths and strict build markers. Never run an old
host after a failed build. V7 settings require explicit track scope; its VMM
media and part-effect paths are unsupported. See `docs/vocaloid7.md`; historical
V6 acceptance is not V7 acceptance. Keep the existing MCP registration name.

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
- [x] Agent song workflow at 0.27.0: 39 tools with `vocaloid_workflow`, lyric conversion on edit, written-form hints and applicability markers, backed by a sample-exact audit of what VOCALOID:AI sings.
- [x] 0.28.0 automatic temporary-file cleanup at server start and every 10 minutes (1 h cutoff), manual dry-run/apply tool, and a `vocaloid_status.temp_cleanup` receipt.
- [ ] Complete editor-feature coverage fully validated.
- [x] 0.29.0: V6/V7 selection and isolated builds; default VoiceType migration;
	both products passed bounded stdio compose/save/reopen/nonzero-WAV checks.
	Pure V7 asa file editing/G2PA roundtrip passed. 39 tools / 128 indexed operations
	includes the previously omitted existing batch.run; V7 unsupported paths remain explicit.
