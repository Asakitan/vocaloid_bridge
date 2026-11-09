# DAW IPC isolation investigation

Date: 2026-11-10. This is a read-only file audit, not a plugin or DAW test.
No plugin, editor, Cubase, MIDI port or microphone was opened. File offsets
below are hexadecimal byte offsets; instruction locations are PE RVAs.

## Installed plugin evidence

| File under `C:/Program Files/Common Files/VST3` | Static evidence |
| --- | --- |
| `VOCALOID VSTi.vst3` (3,336,704 bytes) | ASCII request and notification identifiers at `0x285c78` and `0x285ca0`; pipe prefix at `0x285cd8`; `yamaha.vocaloid.shm` at `0x285d58` and `Local\` at `0x285d74`. |
| `VOCALOIDBridge.vst3` (3,338,752 bytes) | The same request and notification identifiers at `0x283d88` and `0x283db0`; pipe prefix at `0x283de8`; RTTI includes `IPCController` and an ARA `MainDocumentController`. |

The two identifiers are `com.yamaha.vocaloidrequest.version1` and
`com.yamaha.vocaloidnotification.version1`. Both binaries have calls to
`CreateFileA`, `CreateNamedPipeA`, and `ConnectNamedPipe`, and code referencing
the `\\.\pipe\` prefix. VSTi references occur at RVAs `0x44403`, `0x45410`,
`0x446e9`, `0x45abb` and `0x45af6`; Bridge references occur at `0x53f22`,
`0x54b76`, `0x542c5`, `0x5515b` and `0x55196`. The prefix is concatenated
with an incoming value in the inspected routines. Collision behavior and
runtime peer ownership remain unresolved.

Further static caller tracing resolves the name arguments for these two paths.
VSTi function RVA `0x47820` reads global pointers at RVAs `0x286108` and
`0x286110`, whose PE-initialized values point respectively to the request and
notification strings. It passes them to the prefix-building constructors at
`0x442e0` and `0x45320`. Bridge function `0x4ec40` reads globals at `0x282d88`
and `0x282d90` pointing to the same respective strings, and passes them to
constructors `0x54a90` and `0x53e20`. In each constructor the inspected code
concatenates its name argument directly to the nine-byte pipe prefix. The
subsequent file and named-pipe API calls in their corresponding object paths
indicate VSTi client request / server notification and Bridge server request /
client notification, respectively. These are fixed names on these static
paths; there is no PID argument in the inspected name construction. API
execution conditions, potential global mutation, other pathways and peer
authentication are not established. Thus a private desktop and the PID-scoped
mapping do not separate these identified pipe names from an existing peer.
Do not load either plugin on that basis.

### Security arguments and coverage

Both identified server calls pass a null `lpSecurityAttributes`: at VSTi
`0x45a3b` zeroes `r15d`, and `0x45a93` stores `r15` into stack argument 8
before `CreateNamedPipeA` at `0x45abb`; Bridge `0x550e5` zeroes `r14d`,
and `0x55133` supplies it before the call at `0x5515b`. Microsoft documents
[the null parameter](https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-createnamedpipew)
as selecting the pipe's default security descriptor. This is a static call-site
finding, not a measurement of the effective ACL or peer token in a running
instance. Both identified client calls use `GENERIC_WRITE`, null security
attributes, and `OPEN_EXISTING`; the synthetic test requested both read and
write, so its access result does not directly establish the write-only case.

A PE exception-function bounded x64 disassembly found one direct imported
`CreateNamedPipeA`, one `ConnectNamedPipe`, and one `CreateFileA` call in each
plugin (the locations above). It found five `CreateFileW` call sites in each:
VSTi `0x160fae`, `0x16100c`, `0x16122c`, `0x162cca`, `0x162d84`; Bridge
`0x15deee`, `0x15df4c`, `0x15e16c`, `0x15f816`, `0x15f8d0`. Their filenames
and purposes have not been traced. Both import and call `GetProcAddress` and
`LoadLibrary`; therefore this scan does not exclude dynamically resolved APIs,
other libraries' IPC, indirect calls, code outside unwind ranges, or process
discovery. No conclusion that the two named paths are exhaustive is justified.

Microsoft's [ConnectNamedPipe documentation](https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-connectnamedpipe)
states that named pipes within app-containers must use the `\\.\pipe\LOCAL\`
syntax. The statically constructed plugin names lack that segment. This makes
direct use by an AppContainer-hosted plugin a compatibility concern, not a
measured failure for these binaries: this audit did not load them or attempt
their endpoints. A sandbox plan must establish both isolation and a working
plugin-to-plugin route without assuming that these fixed names are rewritten.

In VSTi, the code around RVA `0x45db5` calls `GetCurrentProcessId`, passes the
result with `%d` to a formatting routine, and constructs a string from
`Local\`, `yamaha.vocaloid.shm`, `.`, and that formatted buffer. That string
is passed as the name to `CreateFileMappingA` at RVA `0x46105`. The call uses
the paging file, size 8 bytes, and default security attributes; subsequent code
checks error `0xb7` (already exists). This is static evidence of a PID-derived
local mapping on this path, not a general isolation guarantee for the plugin.
In particular, the pipe client/server paths above are separate, and the rest of
the process-discovery and communication paths are not yet traced. `Local\`
does not isolate processes on separate desktops in the same Windows session.

The VSTi also contains messages about another running Editor/VSTi/AU and a
Bridge connection; Bridge contains ARA loading and VSTi connection messages.
Their presence does not establish when they execute. The PDB path strings
reference release `6.13.3`, and a nearby VSTi string reads `6.13.3.1`; neither
is a runtime version query. The installed editor's corresponding call paths
and any dynamically resolved endpoints remain unexamined.

The scan read PE bytes with `pefile` and decoded x64 executable sections with
Capstone, matching RIP-relative references to literals and imported API slots.
Linear decoding may miss code or produce false instruction boundaries; review
the function control-flow graph and all references before drawing exhaustive
conclusions. Results apply only to these installed binaries.

## Host contract and remaining gate

Steinberg's [module loading documentation](https://steinbergmedia.github.io/vst3_dev_portal/pages/Technical%2BDocumentation/VST%2BModule%2BArchitecture/Loading.html)
describes factory-based loading. Its [processor interface](https://steinbergmedia.github.io/vst3_doc/vstinterfaces/classSteinberg_1_1Vst_1_1IAudioProcessor.html)
requires processing setup and component activation before `setProcessing(true)`
and processing; process data carries buffers, events, parameter changes and
context. Query [IProcessContextRequirements](https://steinbergmedia.github.io/vst3_dev_portal/pages/Technical%2BDocumentation/Change%2BHistory/3.7.0/IProcessContextRequirements.html)
between initialization and activation, and supply supported requested context
with valid flags and actual host time. Follow SDK threading, bus negotiation,
state and cleanup contracts. A generic VST3 host alone does not implement ARA
document hosting or prove that this plugin works without a UI.

Before loading, trace endpoint construction and discovery, access controls and
cleanup across both plugins and editor dependencies, including dynamically
resolved IPC. Prove a boundary that excludes every existing editor and host
endpoint on every initialization path. Then implement a separately owned host
lifecycle and test actual processing and transport only after that gate. A
private desktop or PID-derived mapping alone is insufficient. No synthetic
clock or fabricated connection establishes DAW synchronization.

## AppContainer candidate, not yet validated

[Microsoft's IPC guidance](https://learn.microsoft.com/en-us/windows/apps/develop/communication/interprocess-communication)
describes same-package named-pipe restrictions for packaged applications and
distinguishes full-trust processes. The [Win32 AppContainer launch guide](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)
documents a profile, SID and `SECURITY_CAPABILITIES`; its documented derivation
path is for an existing profile. Deriving an arbitrary SID without registering a
profile is an experiment, not an established supported profileless contract.
Never infer that an arbitrary process is restricted merely from its desktop.

A non-invasive experiment can generate a unique random pipe name, have an owned
full-trust server create it, then launch an owned tiny child with a distinct
AppContainer SID and no capabilities via `STARTUPINFOEX` and
`PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES`. The child reports its actual
token's `TokenIsAppContainer` and SID, attempts only the synthetic name, and
reports the exact result; a matching full-trust child provides a positive
control. Test synthetic server creation by the restricted process separately,
including both ordinary and `LOCAL\` names, and compare error codes. Exit and
close every owned process and handle; no VOCALOID names, plugin, editor,
existing endpoint or persistent profile is involved. Process launch failure or
access denial is an observed result, not proof of an entire isolation boundary.

An initial focused probe was executed using `tools/probe_appcontainer_pipe.cs`
and the .NET Framework C# compiler, with an elevated command because the
default sandbox denied the compiler's temporary resource file. The machine
receipt is `artifacts/probe-appcontainer-pipe.txt`: creation of a unique
profile returned `0x00000000`, a full-trust control connected to the random
pipe with exit code 0, and the restricted child did not exit within 10 seconds.
The harness terminated that child and profile deletion returned `0x00000000`.
The restricted child's token and pipe result were not observed. Thus this run
does not establish either denial or successful isolation. The profile is
temporary rather than profileless, and the deletion HRESULT is the recorded
cleanup result, not an independent storage audit. The C# test launches only
its own executable and uses a GUID-derived pipe, never a VOCALOID name.

The initial test did not explicitly specify a private desktop or no-window
creation; subsequent runs use a newly created private desktop and
`CREATE_NO_WINDOW`. A stage-instrumented repeat writes child output to an
inherited anonymous pipe and records `artifacts/probe-appcontainer-pipe-stages-v2.txt`.
The ordinary child reached managed main, reported `TokenIsAppContainer=0`,
and connected to the synthetic pipe. The restricted child exited with
`0xC06D007E` without any captured stage; its token and `CreateFile` outcome
remain unobserved. This differs from the original timeout and does not identify
its root cause: a missing stage can reflect startup or output-path failure.
The probe does not distinguish CLR initialization from inherited-handle or
desktop-access problems. Profile deletion returned success and the desktop
handle closed successfully. The preceding `stages.txt` receipt incorrectly
interprets the abnormal process status as a pipe error; that interpretation
was corrected in the probe and must not be used.

A subsequent native Go child (`tools/probe_appcontainer_child.go`) uses the
same private-desktop, no-window parent and anonymous stage output. Receipt
`artifacts/probe-appcontainer-native-child.txt` records profile creation and
deletion HRESULT `0`, successful desktop close, a full-trust positive control
(`TokenIsAppContainer=0`, pipe error 0), and restricted child
`TokenIsAppContainer=1` with `CreateFileW` error 5 (`ERROR_ACCESS_DENIED`) on
the random full-trust-created pipe. Both children exited and their process and
thread handles were closed. This isolates an observed difference to the managed
child's startup/output environment, not the precise cause of its earlier
timeout or abnormal exit. The native result establishes only denial against
this synthetic server's default security descriptor and this token on this
machine. It does not establish the result for Yamaha's descriptors, reverse
direction, pipe namespace handling, discovery mechanisms, or plugin startup.

Reproduce from the workspace with Go and the .NET Framework C# compiler:

```powershell
$env:GOCACHE = Join-Path (Get-Location) 'artifacts\go-cache'
& 'C:\Program Files\Go\bin\go.exe' build -o artifacts\probe_appcontainer_child.exe tools\probe_appcontainer_child.go
& C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /nologo /out:artifacts\probe_appcontainer_pipe.exe tools\probe_appcontainer_pipe.cs
& artifacts\probe_appcontainer_pipe.exe artifacts\probe_appcontainer_child.exe
```

Even a passing probe would not prove
that VOCALOID licensing, installed DLLs, user files, registry or audio work in
the container, or that the plugin's IPC and process-discovery paths are covered.
It might also make the fixed non-`LOCAL` pipe names unusable, preventing the
intended VSTi/Bridge connection. Preserve the existing native project engine;
do not load a plugin until isolation, access requirements and real transport
behavior are demonstrated independently.

### Synthetic restricted-server and peer controls

A follow-up used only GUID-derived synthetic names and transient profiles; no
plugin or user endpoint was touched. `tools/probe_appcontainer_server.cs` and
`tools/probe_appcontainer_server_child.go` produced
`artifacts/probe-appcontainer-server.txt`: full-trust ordinary-name server
creation returned Win32 0; an AppContainer child (`TokenIsAppContainer=1`)
returned Win32 5 for the same ordinary syntax and 0 for `LOCAL` syntax. The
child closes any successful pipe handle before exit. All three child exits
were 0, profile deletion HRESULT was 0, and desktop close returned true.

`tools/probe_appcontainer_peer.cs` and `tools/probe_appcontainer_peer_child.go`
produced `artifacts/probe-appcontainer-peer-controls.txt`. Two separately
created transient profiles were used. For each case the server created a fresh
random `LOCAL` pipe with default security and `FILE_FLAG_FIRST_PIPE_INSTANCE`;
the peer sent byte `A` and received byte `B`. Both same-profile children
reported `TokenIsAppContainer=1`, both reported `exchange_ok`, and both exited
0. A client from the second profile reported AppContainer 1, repeatedly got
file-not-found (Win32 2), and exited 4; the server timed out and the parent
terminated and waited for that owned child. A full-trust client reported
AppContainer 0 and the same file-not-found and exit 4; its server likewise
was terminated after timeout. Both profile deletion HRESULTs were 0 and desktop
close returned true. The harness uses the distinct profile SIDs provided by
`CreateAppContainerProfile` but reports only token type, not the SID value;
it does not independently audit profile storage or check termination return
codes. Case labels and receipts, rather than the harness overall exit status,
are the evidence. Its fixed timeouts and retry loop are probe mechanics, not a
production host design.

These controls establish a synthetic same-profile LOCAL byte exchange and
observed non-discovery by two other token contexts on this machine. They do
not establish an access boundary for other IPC mechanisms or for the vendor's
fixed non-LOCAL names. In particular, this result does not make those plugin
paths usable inside AppContainer. Runtime plugin, licensing, host, process
discovery, network, files, registry, shared memory and audio requirements remain
unexamined; private desktop remains separate from IPC isolation.

Reproduce the two focused probes with the compiler commands above, replacing
`probe_appcontainer_child.go` and `probe_appcontainer_pipe.cs` respectively
with `probe_appcontainer_server_child.go` / `probe_appcontainer_server.cs`,
then `probe_appcontainer_peer_child.go` / `probe_appcontainer_peer.cs`. Run each
parent executable with its corresponding child executable path. The peer
negative cases deliberately wait for timeout before terminating each server.

### Token and cleanup follow-up

The peer probe now records `TokenAppContainerSid` from each restricted child's
actual process token, and records the termination and wait results for timed-out
servers. In `artifacts/probe-appcontainer-peer-sid-controls.txt`, the same-SID
server and client reported identical SIDs and exchanged the two bytes; the
different-profile client reported a distinct SID and Win32 2, as did the
full-trust client. Both negative-case servers reported `terminate=True` and
`wait_result=0`; both profile deletion HRESULTs were zero and desktop close
returned true. The full-trust process reported `TokenIsAppContainer=0`.
This receipt does not independently audit deleted profile storage, and its
case-level results, not the parent exit code, establish the observations.

Microsoft's [named-pipe API documentation](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createnamedpipea)
specifies `LOCAL` syntax in its AppContainer guidance, while its
[IPC guidance](https://learn.microsoft.com/en-us/windows/apps/develop/communication/interprocess-communication)
also distinguishes packaged and full-trust processes and describes sharing
across packages. Neither document establishes automatic rewriting of a
non-`LOCAL` name. At the time of that peer receipt, no mapping or vendor protocol
compatibility had been tested; the subsequent controlled mapping experiments are
described below. The synthetic exchange is not evidence of an operational DAW,
plugin or ARA host. Remaining isolation coverage includes all other IPC, discovery, token,
file, registry, network, licensing and audio paths.

### Explicit synthetic name translation

`tools/probe_appcontainer_mapping.cs` launches only its own native Go child on
a private desktop using two transient AppContainer profiles. The child accepts
only names beginning with the random `CodexSynthetic` prefix and explicitly
translates `\\.\pipe\CodexSynthetic...` to
`\\.\pipe\LOCAL\CodexSynthetic...` before calling the Win32 API. It logs
the original and translated names and the actual AppContainer token SID. This
is application-level opt-in translation in a single executable, **not** an
interposition mechanism, synthetic DLL, or modification of any plugin.

In `artifacts/probe-appcontainer-mapping-controls.txt`, the raw same-profile
server failed with access denied and its client saw file-not-found. With
translation enabled, both same-profile peers reported identical SIDs and each
completed a one-byte send/receive exchange. A second-profile client with a
distinct SID and a full-trust client each saw file-not-found; both waiting
servers reported `terminate=True` and `wait_result=0`. Both profile deletion
HRESULTs were zero and desktop close returned true. This is evidence for this
controlled name translation and token configuration only; profile storage was
not independently audited. The client/server roles and case-level exits in the
receipt matter; the harness exit alone is not an acceptance result.

This does not establish that a fixed-name binary can be redirected without
source changes: import-table calls, dynamically resolved APIs, alternate name
encodings and APIs, spawned processes, collisions, peer authentication and
other IPC have not been covered. No vendor names or binary were used. A
separate synthetic DLL and host were not part of this experiment; it cannot
justify loading the real plugin or claim VST3/ARA compatibility. Compile and run the same way as the peer controls,
using the `probe_appcontainer_mapping` parent and child filenames instead.

### Synthetic static-import interception

An installed Visual Studio 2022 Build Tools MSVC 14.44 compiler and Windows SDK
were found locally; no toolchain download, installation or global PATH change
was needed. `tools/probe_mapping_dll.c` builds a synthetic DLL with static
`CreateNamedPipeW` and `CreateFileW` imports. The separate
`tools/probe_mapping_patch.c` locates those two named imports in that module's
import table and replaces their slots with wrappers that accept only
`CodexSynthetic` names and insert `LOCAL`. `tools/probe_appcontainer_iat_child.go`
loads only those two owned DLLs and invokes their exported entry points;
`tools/probe_appcontainer_mapping.cs` supplies the private desktop, random
names and profiles. Patch result zero means both slots were found and updated.

The first receipt, `artifacts/probe-appcontainer-iat-controls.txt`, records
restricted DLL load access denied and does not test the interception. For the
follow-up, only the two newly compiled DLL files received a temporary explicit
`ALL APPLICATION PACKAGES` read/execute ACE. In
`artifacts/probe-appcontainer-iat-controls-acl.txt`, the raw same-SID server
reported access denied and client reported file-not-found; after patching, the
same-SID pair each reported exchange success. A distinct-SID client and a
full-trust client each reported file-not-found; both waiting servers reported
successful termination and wait. Both profile deletions returned HRESULT zero,
and desktop close returned true. The temporary ACEs were removed immediately
afterward; `icacls` showed the same inherited entries as before. The harness's
case output, not its aggregate exit status, is the evidence.

This proves only this controlled x64 DLL's two static wide-character imports
and synthetic byte exchange. It does not cover ANSI APIs, delay imports,
dynamic resolution, other DLLs, child processes, alternate pipe paths,
initialization-time calls before patching, permissions, races, licensing,
discovery or other IPC. The code is a test probe, not a general interposer or
production host; it does not patch or load any Yamaha binary. It does not
establish real plugin isolation, VST3/ARA behavior or transport synchronization.

### ANSI import and timing boundary probe

`tools/probe_iat_ansi_fixture.c` and `tools/probe_iat_ansi_host.c` add a
separate x64 full-trust synthetic probe, not an AppContainer test. The host
generates an externally supplied `CodexSynthetic`-prefixed random pipe name;
the fixture creates and closes only that name. Its `DllMain` performs one
creation before `LoadLibrary` returns. After loading, the host patches only
that module's static `CreateNamedPipeA` and `CreateFileA` import slots with
counting wrappers that deliberately return `ERROR_INVALID_NAME`; these are
interception controls, not name-translation wrappers. It then invokes a
`GetProcAddress`-resolved `CreateNamedPipeA` and loads a second copy of the
owned fixture without patching it. The test uses no vendor binary or endpoint.

In `artifacts/probe-iat-ansi-boundary.txt`, initialization creation returned
Win32 0 before patching; two slots were patched; the static create and
write-only open calls each reached a wrapper (cumulative counts 1 and 2),
while the dynamically resolved create succeeded without increasing the count.
The second module's initialization and static create also succeeded without
increasing the count. The process exited 0 and closed successful pipe handles.
This demonstrates the specific bypasses of a post-load per-module IAT patch,
not that ANSI name translation works or that a dynamic-resolution hook is
complete. No same-profile exchange or isolation was tested in this probe.
Microsoft documents that [GetProcAddress returns an exported address](https://learn.microsoft.com/en-us/windows/win32/api/libloaderapi/nf-libloaderapi-getprocaddress)
and that [DllMain runs under the loader lock](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-best-practices);
these observations do not establish the initialization behavior of the vendor
plugins. Delay imports, alternate APIs, load races, other processes, actual
AppContainer ANSI behavior and all real plugin paths remain unverified.

The first compiler invocation failed with permission denied for its object
file under the sandbox; the successful isolated probe was compiled and run
with elevated execution. The fixture makes a named-pipe call in `DllMain`
only to measure this timing boundary; it is not a recommended production
initialization pattern.
