# Native API Catalog and Byref Arguments

## Scope and Evidence

`api_catalog` inventories metadata from the assembly that actually supplies
`Yamaha.VOCALOID.VSM.WIVSMSequence` in the running native host. It runs before
session lookup and requires no `session_id`. It does not create a project,
invoke a native member, evaluate a property, read a field value, inspect an
activation record, or initialize an alternate engine.

The catalog covers all types in that assembly, including nonpublic and
non-VSM types. Their exclusions remain visible by default. It is not a catalog
of every assembly installed with the editor. A member marked `supported` has
passed the RPC signature and access policy, not a functional/native-engine test.
Availability still requires an appropriate live session object, native state,
and installed resources. Metadata alone does not establish full editor parity.

## Request

```json
{"id":1,"method":"api_catalog","params":{"namespace":"Yamaha.VOCALOID.VSM","include_excluded":true,"include_members":true,"offset":0,"limit":25}}
```

| Parameter | Type | Default | Meaning |
| --- | --- | --- | --- |
| `type` | string or null | null | Exact CLR full type name, including `+` for nested types. |
| `namespace` | string or null | null | Exact namespace; null includes all namespaces in the installed assembly. |
| `include_excluded` | boolean | true | Retain excluded types and members with their reasons. |
| `include_members` | boolean | true | Include declared members; false returns empty `members` arrays. |
| `offset` | integer | 0 | Filtered type offset, 0..100000. |
| `limit` | integer | 25 | Type page size, 1..100. |

Filters combine with AND. Unknown exact names return an empty page. Pagination
counts types, not members, after the filters are applied. Types are sorted by
full name with ordinal comparison; members are ordered by kind, name, then
signature. Use `namespace: "Yamaha.VOCALOID.VSM"` for the normal object surface.
Enumerating outside it is informational and does not grant callable access.

## Response

The normal JSON-lines envelope is `{ "id": 1, "result": CATALOG }`. Failures
retain the existing `{ "id": 1, "error": { "type": ..., "message": ... } }`
envelope, including assembly/reflection failures. Partial catalog data is not
silently substituted if type loading fails.

| Catalog field | Type | Meaning |
| --- | --- | --- |
| `assembly` | object | Actual assembly `name` and `version` strings, nullable if absent in metadata. |
| `type`, `namespace` | string or null | Echoed exact filters. |
| `include_excluded`, `include_members` | boolean | Echoed selection flags. |
| `offset`, `limit` | integer | Echoed type pagination. |
| `total` | integer | Total filtered types before pagination. |
| `has_more` | boolean | More filtered types follow this page. |
| `types` | array | Type descriptors for this page. |

Each type descriptor contains:

| Field | Type | Meaning |
| --- | --- | --- |
| `type` | string | Exact CLR full name. |
| `kind` | string | `enum`, `interface`, `delegate`, `struct`, or `class`. |
| `base_type` | string or null | CLR base type; query its catalog entry for inherited native members. |
| `visibility` | string | `public` or `nonpublic`, including enclosing-type visibility. |
| `supported` | boolean | Type is admitted by the VSM object/data policy. |
| `reason` | string or null | First exclusion reason, or null when admitted. |
| `constructible` | boolean | Safe enum/default data-struct construction is available. Not a claim that every constructor is admitted. |
| `declared_only` | boolean | Always true: inherited declarations are inventoried on their declaring type. |
| `members` | array | Declared constructors, methods, properties, fields, and events. |

All member descriptors contain `kind`, `name`, `declaring_type`, `supported`, and
nullable `reason`. Member kinds are `constructor`, `method`, `property`, `field`,
and `event`. Only metadata is returned, including for excluded members.

Methods and constructors also contain `member_id`, `return_type`, `parameters`,
`static`, and `visibility`. Constructor `return_type` is its declaring type.
`member_id` remains the existing exact overload identifier:
`NAME(CLR_TYPE_0,CLR_TYPE_1,...)`. Byref CLR types include the trailing `&`.
Take real identifiers from a response; do not synthesize signatures.

Parameter descriptors contain:

| Field | Type | Meaning |
| --- | --- | --- |
| `name` | string or null | Metadata parameter name. |
| `type` | string | Exact CLR parameter type, including `&` for byref. |
| `value_type` | string | CLR element type for byref, otherwise the ordinary type. |
| `direction` | string | `out` for output-only byref; `in` for ordinary/input-only arguments; `ref` for remaining byrefs. |
| `optional` | boolean | CLR optional metadata; the RPC still requires every position. |

Properties and fields also contain `type`, `static`, `can_read`, `can_write`,
`read_reason`, and `write_reason`. Properties include index `parameters`, even
though indexed property calls are excluded. Static data can only be read;
read-only fields and missing/nonpublic accessors retain per-access reasons.
Events report their handler `type` and remain excluded. Constants, defaults,
and live field/property values are not read by this operation.

`members` remains the separate session-level, inherited callable-object view.
Its ordinary result keys and exact method IDs are unchanged. Its parameter
descriptors now additionally expose `value_type`, `direction`, and `optional`.

## Ref, Out, and Input-Only Byref

`call` and explicitly selected data-struct constructors accept byref parameters
only when their element type is a supported scalar, safe native enum, or
pointer-free native data struct. Nullable versions are accepted. Native object
references, collections, pointers, pointer-bearing layouts, delegates, and
arbitrary managed objects are not allowed as byref elements.

Arguments remain positional and must match the full parameter count:

- Ordinary, `ref`, and input-only byref positions use the existing typed JSON
  value or compatible session `$ref` representation.
- An output-only `out` position must contain JSON `null`. The host supplies its
  typed default; a supplied non-null input is rejected before native invocation.
- For any signature with byrefs, the result contains `value` plus an `out_args`
  array. Each output/ref entry has `index`, `name`, `type`, and `value`. The index
  is zero-based and `type` is the element CLR type without `&`.
- Input-only byref positions are not included in `out_args`. A signature with
  only input-only byrefs returns an empty `out_args` array.
- Output scalars and enums use normal serialization; output structs are new
  session `$ref` values that can be inspected with `get`/`members`.

This is explicit copy-in/copy-out, not a writable pointer bridge. A struct input
`$ref` is a value source; callers must consume the returned output value and
explicitly set any desired project destination. Repeated JSON references do not
request CLR aliasing. This does not create a way to replace the native objects
owned by a session. Native exceptions retain the existing error envelope and
do not produce successful output-argument records.

Ordinary calls and constructors without byrefs retain exactly `{ "value": ... }`.
Existing optional-argument, dirty-state, child-reference invalidation, numeric,
enum, collection, and same-session reference checks remain in force.

## Retained Exclusions

The same predicates decide invocation eligibility and catalog reasons. The
catalog exposes the first applicable reason, not a claim that later constraints
would pass. Important reason families are:

| Reason | Retained boundary |
| --- | --- |
| `outside_installed_assembly`, `outside_vsm_namespace` | No arbitrary System or foreign assembly access. |
| `type_not_public`, `member_not_public` | Nonpublic declarations are metadata only. |
| `open_generic_type`, `open_generic_method` | No open generic construction/invocation. |
| `pointer_or_stack_only_type`, `pointer_or_unsupported_data_layout` | No native pointer, function-pointer, stack-only, or unsupported value layout access. |
| `callbacks_and_delegates_not_exposed`, `callbacks_and_events_not_exposed` | No arbitrary callback, observer, or event registration. |
| `host_owned_lifecycle_type`, `native_wrapper_construction_owned_by_host` | Managers and raw wrappers remain owned by the host. |
| `restricted_name:WORD` | Existing secret, authorization, UI/window, pointer/handle, file/path, script, device/playback, process/thread, and manager name filters remain active. |
| `host_owned_operation:PREFIX` | Generic lifecycle, persistence, import/export, UI, playback, rendering, and recording entry points stay restricted. |
| `static_method_not_exposed`, `varargs_not_exposed`, `runtime_object_method_not_exposed` | No static executable, varargs, or arbitrary runtime-object surface. |
| `accessor_or_special_method_use_property_api`, `indexed_property_not_exposed` | Property access follows the existing checked property API. |
| `unsupported_return_type:TYPE`, `unsupported_property_type:TYPE`, `unsupported_field_type:TYPE` | Result/member type cannot be safely serialized. |
| `unsupported_parameter:INDEX:NAME:TYPE`, `unsupported_byref_parameter:INDEX:NAME:TYPE` | Input or byref type cannot be safely converted. |
| `static_write_not_exposed`, `no_public_getter`, `no_public_setter_or_readonly_field` | Per-access read/write restrictions. |

The only added operation-prefix exception is the exact public instance method
`WIVSMMidiPart.RenderableNoteDuration(System.Int32) -> System.Int32`, treated as
read-only. The retained decompilation in
`artifacts/reverse/WIVSMMidiPart/Yamaha.VOCALOID.VSM.WIVSMMidiPart.decompiled.cs`
shows it directly returning the native duration query. No other `Render*`
method is admitted by that exception; it is not a WAV synthesis route.

## Reviewed Dispatch Routes

The dispatcher separately forwards session `score_edit` to
`host.EditScore(session.Id, operation, options)` and `audio_op` to
`host.AudioOperation(session.Id, operation, options)`. `operation` is a required
string and `options` is required; the Python layer supplies an object. Their
operation validation belongs to the respective host implementations, not this
generic metadata dispatcher.

The coordinating parent additionally owns `import_project` and `export_midi`.
Their dedicated routes do not remove generic file/path or lifecycle exclusions.
`import_project` is global with required `path`, `code_page=65001` converted to a
checked UInt32, and `prefer_ai=true`; `export_midi` is session-scoped with required
`output_name`, `encoding="Utf8"`, and `overwrite=false`. The host implementations
remain responsible for paths, formats, and ownership.

## Validation Boundary

This slice was checked with editor diagnostics, not a native build or live
catalog/byref invocation while sibling writers were active. Integrated native
compilation and real engine validation belong to the coordinating parent after
all writer changes are present. No fabricated catalog counts, byref successes,
or full-feature coverage claims are recorded here.