using System.Collections;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text;
using System.Text.Json;
using Yamaha.VOCALOID.VSM;

internal sealed class RpcServer(EngineHost host, string desktop)
{
    private const string NativeNamespace = "Yamaha.VOCALOID.VSM";
    private const BindingFlags PublicMembers = BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static;
    private const int MaxLineLength = 1024 * 1024;
    private static readonly Assembly NativeAssembly = typeof(WIVSMSequence).Assembly;
    private static readonly string[] ForbiddenNames =
    [
        "License", "Activation", "Serial", "ProductKey", "Secret", "Password", "Credential", "Authorization",
        "Window", "Dialog", "Hwnd", "Pointer", "Handle", "Callback", "Observer", "Clipboard", "Lua", "Script",
        "DatabaseManager", "DSEManager", "File", "Path", "Device", "Playback", "AudioOutput", "Process", "Thread"
    ];
    private static readonly string[] ForbiddenOperations =
    [
        "Open", "Close", "Save", "Dispose", "Destroy", "Create", "Load", "Export", "Import", "Show", "Browse",
        "Launch", "Start", "Stop", "Play", "Record", "Render"
    ];

    internal int Run(TextReader input, TextWriter output)
    {
        while (true)
        {
            (string? line, bool tooLong) = ReadLine(input);
            if (line is null)
                return 0;
            int? id = null;
            object response;
            try
            {
                if (tooLong)
                    throw new ArgumentException("Request exceeds the 1 Mi-character line limit.");
                using JsonDocument document = JsonDocument.Parse(line, new JsonDocumentOptions { MaxDepth = 64 });
                JsonElement request = document.RootElement;
                if (request.ValueKind != JsonValueKind.Object)
                    throw new ArgumentException("Request must be an object.");
                if (request.TryGetProperty("id", out JsonElement rawId) && rawId.TryGetInt32(out int requestId))
                    id = requestId;
                ValidateObjectKeys(request);
                if (id is null)
                    throw new ArgumentException("id must be a 32-bit integer.");
                string method = RequiredString(request, "method");
                JsonElement parameters = request.TryGetProperty("params", out JsonElement supplied)
                    ? supplied : throw new ArgumentException("params must be an object.");
                if (parameters.ValueKind != JsonValueKind.Object)
                    throw new ArgumentException("params must be an object.");
                response = new { id, result = Dispatch(method, parameters) };
            }
            catch (Exception error)
            {
                while (error is TargetInvocationException { InnerException: not null } invocation)
                    error = invocation.InnerException!;
                response = new { id, error = new { type = error.GetType().Name, message = error.Message } };
            }
            output.WriteLine(JsonSerializer.Serialize(response));
            output.Flush();
        }
    }

    internal object Dispatch(string method, JsonElement parameters)
    {
        if (method == "ping")
            return new { backend = "native-vsm", pid = Environment.ProcessId, version = EngineHost.EngineVersion, sessions = host.SessionCount, desktop, cache_namespace = host.CacheNamespace, render_cache_bytes = host.RenderCacheBytes };
        if (method == "api_catalog")
            return ApiCatalog(parameters);
        if (method == "create")
            return host.Create(RequiredString(parameters, "title"), Number(parameters, "bpm", 120), Integer(parameters, "sample_rate", 44100)).Summary();
        if (method == "open")
            return host.Open(RequiredString(parameters, "path")).Summary();
        if (method == "import_project")
            return host.ImportProject(RequiredString(parameters, "path"), checked((uint)Integer(parameters, "code_page", 65001)), Boolean(parameters, "prefer_ai", true)).Summary();
        if (method == "voices")
            return host.Voices();
        if (method == "midi_recording")
        {
            string? id = OptionalString(parameters, "session_id");
            string operation = RequiredString(parameters, "operation");
            JsonElement options = Required(parameters, "options");
            if (operation != "devices")
                host.CheckMidiStart(host.GetSession(id ?? throw new ArgumentException("session_id is required.")), operation);
            object result = host.MidiRecordingOperation(id, operation, options);
            return new { session_id = id, operation, native = true, result };
        }
        if (method == "library_op")
        {
            string? id = OptionalString(parameters, "session_id");
            string operation = RequiredString(parameters, "operation");
            JsonElement options = Required(parameters, "options");
            host.CheckSessionExternalAccess(id);
            if (!host.IsIndependentArchiveLibraryOperation(id, operation, options))
                host.CheckArchiveExternalOperation(id, "library", operation);
            host.CheckFrozenExternalOperation(id, "library", operation);
            return host.LibraryOperation(id, operation, options);
        }
        if (method == "clipboard")
        {
            host.CheckSessionExternalAccess(OptionalString(parameters, "session_id"));
            host.CheckArchiveExternalOperation(OptionalString(parameters, "session_id"), "clipboard", RequiredString(parameters, "operation"));
            host.CheckFrozenExternalOperation(OptionalString(parameters, "session_id"), "clipboard", RequiredString(parameters, "operation"));
            return host.ClipboardOperation(OptionalString(parameters, "session_id"), RequiredString(parameters, "operation"), Required(parameters, "options"));
        }
        EngineSession session = host.GetSession(RequiredString(parameters, "session_id"));
        host.CheckMidiRecordingAccess(session, method, parameters);
        host.CheckTransportAccess(session, method, parameters);
        bool snapshotOutput = host.UsesArchiveOutputSnapshot(session, method, parameters);
        if (!snapshotOutput) host.CheckArchiveRequest(session, method, parameters);
        host.CheckFrozenRequest(session, method, parameters);
        if (snapshotOutput)
            return method switch
            {
                "render_part" => host.ArchiveRenderOutput(session, Unsigned(parameters, "track_index", 0), Unsigned(parameters, "part_index", 0), RequiredString(parameters, "output_name"), Boolean(parameters, "overwrite", false)),
                "export_midi" => host.ArchiveMidiOutput(session, RequiredString(parameters, "output_name"), OptionalString(parameters, "encoding") ?? "Utf8", Boolean(parameters, "overwrite", false)),
                "audio_op" => host.ArchiveAudioOutput(session, RequiredString(parameters, "operation"), Required(parameters, "options")),
                _ => throw new MissingMethodException("Unknown snapshot output operation: " + method)
            };
        return method switch
        {
            "session" => session.Summary(),
            "save" => host.Save(session.Id, RequiredString(parameters, "output_name"), Boolean(parameters, "overwrite", false)),
            "render_part" => host.RenderPart(session.Id, Unsigned(parameters, "track_index", 0), Unsigned(parameters, "part_index", 0), RequiredString(parameters, "output_name"), Boolean(parameters, "overwrite", false)),
            "close" => host.Close(session.Id, Boolean(parameters, "discard", false)),
            "clone_project" => host.CloneProject(session.Id, OptionalString(parameters, "title")).Summary(),
            "revert_project" => host.RevertProject(session.Id, Boolean(parameters, "discard", false)).Summary(),
            "merge_project" => host.MergeProject(session.Id, RequiredString(parameters, "path"),
                Integer(parameters, "offset_tick", 0), Boolean(parameters, "include_tracks", true),
                Boolean(parameters, "include_tempo", false), Boolean(parameters, "replace_tempo", false),
                checked((uint)Integer(parameters, "code_page", 65001))),
            "members" => Members(session, OptionalString(parameters, "ref")),
            "get" => Get(session, OptionalString(parameters, "ref"), RequiredString(parameters, "member")),
            "set" => Set(session, OptionalString(parameters, "ref"), RequiredString(parameters, "member"), Required(parameters, "value")),
            "call" => Call(session, OptionalString(parameters, "ref"), RequiredString(parameters, "member_id"), Arguments(parameters)),
            "construct" => Construct(session, RequiredString(parameters, "type"), OptionalString(parameters, "member_id"), Arguments(parameters)),
            "enumerate" => Enumerate(session, RequiredString(parameters, "ref"), Integer(parameters, "offset", 0), Integer(parameters, "limit", 100)),
            "score_edit" => host.EditScore(session.Id, RequiredString(parameters, "operation"), Required(parameters, "options")),
            "audio_op" => host.AudioOperation(session.Id, RequiredString(parameters, "operation"), Required(parameters, "options")),
            "export_midi" => host.ExportMidi(session.Id, RequiredString(parameters, "output_name"), OptionalString(parameters, "encoding") ?? "Utf8", Boolean(parameters, "overwrite", false)),
            _ => throw new MissingMethodException("Unknown RPC method: " + method)
        };
    }

    private static object ApiCatalog(JsonElement parameters)
    {
        string? typeName = OptionalString(parameters, "type");
        string? namespaceName = OptionalString(parameters, "namespace");
        bool includeExcluded = Boolean(parameters, "include_excluded", true);
        bool includeMembers = Boolean(parameters, "include_members", true);
        int offset = Integer(parameters, "offset", 0);
        int limit = Integer(parameters, "limit", 25);
        if (offset < 0 || offset > 100000 || limit < 1 || limit > 100)
            throw new ArgumentOutOfRangeException(nameof(offset), "offset must be 0..100000 and limit 1..100.");
        Type[] types = NativeAssembly.GetTypes()
            .Where(type => (typeName is null || TypeName(type) == typeName) &&
                (namespaceName is null || type.Namespace == namespaceName) &&
                (includeExcluded || CatalogTypeExclusion(type) is null))
            .OrderBy(TypeName, StringComparer.Ordinal).ToArray();
        AssemblyName assembly = NativeAssembly.GetName();
        return new
        {
            assembly = new { name = assembly.Name, version = assembly.Version?.ToString() },
            type = typeName,
            @namespace = namespaceName,
            include_excluded = includeExcluded,
            include_members = includeMembers,
            offset,
            limit,
            total = types.Length,
            has_more = offset + limit < types.Length,
            types = types.Skip(offset).Take(limit).Select(type => DescribeCatalogType(type, includeExcluded, includeMembers)).ToArray()
        };
    }

    private static object DescribeCatalogType(Type type, bool includeExcluded, bool includeMembers)
    {
        const BindingFlags flags = PublicMembers | BindingFlags.NonPublic | BindingFlags.DeclaredOnly;
        string? reason = CatalogTypeExclusion(type);
        MemberInfo[] members = includeMembers
            ? type.GetMembers(flags).Where(member => member is MethodInfo or ConstructorInfo or PropertyInfo or FieldInfo or EventInfo)
                .Where(member => includeExcluded || CatalogMemberExclusion(member) is null)
                .OrderBy(member => member.MemberType).ThenBy(member => member.Name, StringComparer.Ordinal)
                .ThenBy(member => member is MethodBase method ? MemberId(method) : member.ToString(), StringComparer.Ordinal).ToArray()
            : [];
        return new
        {
            type = TypeName(type),
            kind = type.IsEnum ? "enum" : type.IsInterface ? "interface" : typeof(Delegate).IsAssignableFrom(type) ? "delegate" : type.IsValueType ? "struct" : "class",
            base_type = type.BaseType is null ? null : TypeName(type.BaseType),
            visibility = type.IsVisible ? "public" : "nonpublic",
            supported = reason is null,
            reason,
            constructible = NativeType(type) && (type.IsEnum || IsDataStruct(type)),
            declared_only = true,
            members = members.Select(DescribeCatalogMember).ToArray()
        };
    }

    private static object DescribeCatalogMember(MemberInfo member)
    {
        string? reason = CatalogMemberExclusion(member);
        Dictionary<string, object?> result = new()
        {
            ["kind"] = member is ConstructorInfo ? "constructor" : member is MethodInfo ? "method" : member is PropertyInfo ? "property" : member is FieldInfo ? "field" : "event",
            ["name"] = member.Name,
            ["declaring_type"] = TypeName(member.DeclaringType!),
            ["supported"] = reason is null,
            ["reason"] = reason
        };
        if (member is MethodBase method)
        {
            result["member_id"] = MemberId(method);
            result["return_type"] = method is MethodInfo info ? TypeName(info.ReturnType) : TypeName(method.DeclaringType!);
            result["parameters"] = method.GetParameters().Select(DescribeParameter).ToArray();
            result["static"] = method.IsStatic;
            result["visibility"] = method.IsPublic ? "public" : "nonpublic";
        }
        else if (member is PropertyInfo or FieldInfo)
        {
            bool canRead = reason is null && CanRead(member);
            bool canWrite = reason is null && CanWrite(member) && !IsStatic(member);
            result["type"] = TypeName(SlotType(member));
            result["static"] = IsStatic(member);
            result["can_read"] = canRead;
            result["can_write"] = canWrite;
            result["read_reason"] = canRead ? null : reason ?? "no_public_getter";
            result["write_reason"] = canWrite ? null : reason ?? (member.Name == "IsFrozen"
                ? "requires_structured_freeze_workflow" : IsStatic(member) ? "static_write_not_exposed" : "no_public_setter_or_readonly_field");
            if (member is PropertyInfo property)
                result["parameters"] = property.GetIndexParameters().Select(DescribeParameter).ToArray();
        }
        else if (member is EventInfo eventInfo)
            result["type"] = eventInfo.EventHandlerType is null ? null : TypeName(eventInfo.EventHandlerType);
        return result;
    }

    private static string? CatalogTypeExclusion(Type type) => NativeTypeExclusion(type) ??
        (type.IsValueType && !type.IsEnum && !IsDataStruct(type) ? "pointer_or_unsupported_data_layout" : null);

    private static string? CatalogMemberExclusion(MemberInfo member) => member switch
    {
        MethodInfo method => MethodExclusion(method),
        ConstructorInfo constructor => ConstructorExclusion(constructor),
        PropertyInfo property => PropertyExclusion(property),
        FieldInfo field => FieldExclusion(field),
        EventInfo => "callbacks_and_events_not_exposed",
        _ => "unsupported_member_kind"
    };

    private static object Members(EngineSession session, string? reference)
    {
        NativeReference target = session.Resolve(reference);
        Type type = target.Value.GetType();
        if (CollectionElement(type) is not null)
            return new
            {
                @ref = reference ?? session.RootRef,
                type = TypeName(type),
                properties = new[] { new { name = "Count", type = "System.Int32", can_read = HasCount(target.Value), can_write = false } },
                methods = Array.Empty<object>(),
                constructors = Array.Empty<object>()
            };
        RequireNative(type);
        List<object> properties = [];
        foreach (PropertyInfo property in Properties(type).OrderBy(property => property.Name, StringComparer.Ordinal))
            properties.Add(new { name = property.Name, type = TypeName(property.PropertyType), can_read = property.GetMethod?.IsPublic == true, can_write = property.SetMethod?.IsPublic == true && !IsStatic(property) });
        foreach (FieldInfo field in Fields(type).OrderBy(field => field.Name, StringComparer.Ordinal))
            properties.Add(new { name = field.Name, type = TypeName(field.FieldType), can_read = true, can_write = !field.IsStatic && !field.IsInitOnly && !field.IsLiteral });
        object[] methods = Methods(type).OrderBy(MemberId, StringComparer.Ordinal).Select(DescribeMethod).ToArray();
        object[] constructors = IsDataStruct(type)
            ? type.GetConstructors(BindingFlags.Public | BindingFlags.Instance).Where(SafeConstructor)
                .OrderBy(MemberId, StringComparer.Ordinal).Select(DescribeMethod).ToArray()
            : [];
        return new { @ref = reference ?? session.RootRef, type = TypeName(type), properties, methods, constructors };
    }

    private static object Get(EngineSession session, string? reference, string member)
    {
        NativeReference target = session.Resolve(reference);
        if (CollectionElement(target.Value.GetType()) is not null)
        {
            if (member != "Count" || !HasCount(target.Value))
                throw new MissingMemberException("Only an existing collection Count is readable; use enumerate for items.");
            return new { value = Count(target.Value) };
        }
        MemberInfo slot = Slot(target.Value.GetType(), member);
        object? value = ReadSlot(slot, target.Value);
        Action<object>? writeBack = CanWrite(slot) && !IsStatic(slot)
            ? changed => { WriteSlot(slot, target.Value, changed); target.WriteBack(); }
            : null;
        return new { value = Serialize(session, value, writeBack) };
    }

    private object Set(EngineSession session, string? reference, string member, JsonElement value)
    {
        NativeReference target = session.Resolve(reference);
        MemberInfo slot = Slot(target.Value.GetType(), member);
        if (!CanWrite(slot) || IsStatic(slot))
            throw new InvalidOperationException("Member is not publicly writable on this object.");
        host.CheckArchiveNativeMutation(session, member);
        host.CheckFrozenNativeMutation(session);
        object? converted = ConvertValue(session, value, SlotType(slot));
        EnsureVoiceOperation(target.Value.GetType(), member);
        session.Dirty = true;
        WriteSlot(slot, target.Value, converted);
        target.WriteBack();
        return new { updated = true, value = CanRead(slot) ? Serialize(session, ReadSlot(slot, target.Value)) : null };
    }

    private object Call(EngineSession session, string? reference, string memberId, JsonElement[] arguments)
    {
        NativeReference target = session.Resolve(reference);
        RequireNative(target.Value.GetType());
        MethodInfo method = Methods(target.Value.GetType())
            .SingleOrDefault(candidate => MemberId(candidate) == memberId)
            ?? throw new MissingMethodException("No permitted method has this exact member_id.");
        object?[] converted = ConvertArguments(session, method, arguments);
        bool readOnly = IsReadOnly(method.Name) || ReviewedDataMethod(method);
        if (!readOnly)
        {
            host.CheckArchiveNativeMutation(session, method.Name);
            host.CheckFrozenNativeMutation(session);
            EnsureVoiceOperation(target.Value.GetType(), method.Name);
            session.Dirty = true;
        }
        object? value;
        try
        {
            value = method.Invoke(target.Value, converted);
            if (!readOnly)
                target.WriteBack();
        }
        finally
        {
            if (InvalidatesChildren(method.Name))
                session.InvalidateChildren();
        }
        return InvocationResult(session, method, value, converted);
    }

    private static object Construct(EngineSession session, string typeName, string? memberId, JsonElement[] arguments)
    {
        Type type = NativeAssembly.GetType(typeName, false, false) ?? throw new TypeLoadException("Unknown VSM type.");
        RequireNative(type);
        if (!type.IsEnum && !IsDataStruct(type))
            throw new NotSupportedException("Only public pointer-free VSM data structs and enums may be constructed.");
        object value;
        if (arguments.Length == 0 && memberId is null)
            value = Activator.CreateInstance(type)!;
        else
        {
            if (memberId is null)
                throw new ArgumentException("An exact constructor member_id is required for nonempty args.");
            ConstructorInfo constructor = type.GetConstructors(BindingFlags.Public | BindingFlags.Instance)
                .SingleOrDefault(candidate => SafeConstructor(candidate) && MemberId(candidate) == memberId)
                ?? throw new MissingMethodException("No permitted constructor has this exact member_id.");
            object?[] converted = ConvertArguments(session, constructor, arguments);
            value = constructor.Invoke(converted);
            return InvocationResult(session, constructor, value, converted);
        }
        return new { value = Reference(session, value) };
    }

    private static object Enumerate(EngineSession session, string reference, int offset, int limit)
    {
        if (offset < 0 || offset > 100000 || limit < 1 || limit > 1000)
            throw new ArgumentOutOfRangeException(nameof(offset), "offset must be 0..100000 and limit 1..1000.");
        NativeReference target = session.Resolve(reference);
        if (CollectionElement(target.Value.GetType()) is null)
            throw new ArgumentException("Reference is not an allowed collection or enumerator.");
        List<object?> items = [];
        bool hasMore;
        if (target.Value is IEnumerable enumerable)
        {
            IEnumerator iterator = enumerable.GetEnumerator();
            try
            {
                int skipped = 0;
                while (skipped < offset && iterator.MoveNext())
                    skipped++;
                while (items.Count < limit && iterator.MoveNext())
                    items.Add(Serialize(session, iterator.Current));
                hasMore = iterator.MoveNext();
            }
            finally { (iterator as IDisposable)?.Dispose(); }
        }
        else if (target.Value is IEnumerator iterator)
        {
            Cursor cursor = target.Cursor as Cursor ?? new Cursor(iterator);
            target.Cursor = cursor;
            if (offset < cursor.Position)
                throw new InvalidOperationException("A one-shot enumerator cannot seek backwards; obtain a fresh native enumerator.");
            while (cursor.Position < offset && cursor.Advance(out _)) { }
            while (items.Count < limit && cursor.Advance(out object? item))
                items.Add(Serialize(session, item));
            hasMore = cursor.Peek();
        }
        else
            throw new NotSupportedException("Native collection has no nongeneric enumerable adapter.");
        return new { items, offset, has_more = hasMore };
    }

    private sealed class Cursor(IEnumerator iterator) : IDisposable
    {
        private bool buffered;
        private bool ended;
        private object? next;
        internal int Position { get; private set; }
        internal bool Peek()
        {
            if (!buffered && !ended)
            {
                ended = !iterator.MoveNext();
                if (!ended)
                {
                    next = iterator.Current;
                    buffered = true;
                }
            }
            return buffered;
        }
        internal bool Advance(out object? item)
        {
            if (!Peek()) { item = null; return false; }
            item = next;
            next = null;
            buffered = false;
            Position++;
            return true;
        }
        public void Dispose() => (iterator as IDisposable)?.Dispose();
    }

    private void EnsureVoiceOperation(Type type, string name)
    {
        if (type.Name.Contains("Midi", StringComparison.Ordinal) || type.Name.Contains("Voice", StringComparison.Ordinal) ||
            name.Contains("Midi", StringComparison.Ordinal) || name.Contains("Voice", StringComparison.Ordinal) ||
            name.Contains("Singer", StringComparison.Ordinal) || name == "InsertTrackEx")
            host.EnsureVoiceServices();
    }

    private static object? Serialize(EngineSession session, object? value, Action<object>? writeBack = null)
    {
        if (value is null)
            return null;
        Type type = value.GetType();
        if (type.IsEnum)
            return Enum.GetName(type, value) ?? Convert.ChangeType(value, Enum.GetUnderlyingType(type), CultureInfo.InvariantCulture);
        if (IsScalar(type))
        {
            if ((value is double doubleValue && !double.IsFinite(doubleValue)) ||
                (value is float floatValue && !float.IsFinite(floatValue)))
                throw new InvalidDataException("Native result is not a finite JSON number.");
            if (value is string text && text.Length > MaxLineLength)
                throw new InvalidDataException("Native string exceeds the response string limit.");
            return value;
        }
        Type? element = CollectionElement(type);
        if (element is null)
            RequireNative(type);
        string reference = session.Register(value, writeBack);
        Dictionary<string, object?> result = new() { ["$ref"] = reference, ["type"] = TypeName(type) };
        if (element is not null && HasCount(value))
            result["count"] = Count(value);
        return result;
    }

    private static object Reference(EngineSession session, object value) =>
        new Dictionary<string, object?> { ["$ref"] = session.Register(value), ["type"] = TypeName(value.GetType()) };

    private static object?[] ConvertArguments(EngineSession session, MethodBase method, JsonElement[] values)
    {
        ParameterInfo[] parameters = method.GetParameters();
        if (parameters.Length != values.Length)
            throw new ArgumentException("args must match the exact parameter count, including optional parameters.");
        object?[] converted = new object?[parameters.Length];
        for (int index = 0; index < parameters.Length; index++)
        {
            ParameterInfo parameter = parameters[index];
            if (!SafeParameter(parameter))
                throw new NotSupportedException("Unsupported parameter type: " + TypeName(parameter.ParameterType));
            Type valueType = ParameterValueType(parameter);
            if (parameter.ParameterType.IsByRef && parameter.IsOut && !parameter.IsIn)
            {
                if (values[index].ValueKind != JsonValueKind.Null)
                    throw new ArgumentException("Pure out parameters must use a null argument placeholder: " + parameter.Name);
                converted[index] = valueType.IsValueType ? Activator.CreateInstance(valueType) : null;
            }
            else
                converted[index] = ConvertValue(session, values[index], valueType);
        }
        return converted;
    }

    private static object InvocationResult(EngineSession session, MethodBase method, object? value, object?[] arguments)
    {
        object? serialized = Serialize(session, value);
        ParameterInfo[] parameters = method.GetParameters();
        if (!parameters.Any(parameter => parameter.ParameterType.IsByRef))
            return new { value = serialized };
        return new
        {
            value = serialized,
            out_args = parameters.Where(parameter => parameter.ParameterType.IsByRef && (!parameter.IsIn || parameter.IsOut))
                .Select(parameter => new
                {
                    index = parameter.Position,
                    name = parameter.Name,
                    type = TypeName(ParameterValueType(parameter)),
                    value = Serialize(session, arguments[parameter.Position])
                }).ToArray()
        };
    }

    private static Type ParameterValueType(ParameterInfo parameter) => parameter.ParameterType.IsByRef
        ? parameter.ParameterType.GetElementType()! : parameter.ParameterType;

    private static bool SafeParameter(ParameterInfo parameter)
    {
        Type type = ParameterValueType(parameter);
        if (!parameter.ParameterType.IsByRef)
            return SafeType(type) && type != typeof(void);
        type = Nullable.GetUnderlyingType(type) ?? type;
        return IsScalar(type) || (NativeType(type) && (type.IsEnum || IsDataStruct(type)));
    }

    private static object? ConvertValue(EngineSession session, JsonElement value, Type type, int depth = 0)
    {
        if (depth > 16 || !SafeType(type))
            throw new NotSupportedException("Unsupported argument type or nesting depth.");
        Type? nullable = Nullable.GetUnderlyingType(type);
        if (value.ValueKind == JsonValueKind.Null)
        {
            if (!type.IsValueType || nullable is not null)
                return null;
            throw new ArgumentException("null is not valid for " + TypeName(type));
        }
        if (nullable is not null)
            return ConvertValue(session, value, nullable, depth + 1);
        if (value.ValueKind == JsonValueKind.Object && value.TryGetProperty("$ref", out JsonElement reference))
        {
            if (reference.ValueKind != JsonValueKind.String)
                throw new ArgumentException("$ref must be a string.");
            object resolved = session.Resolve(reference.GetString()).Value;
            if (!type.IsInstanceOfType(resolved))
                throw new ArgumentException("Reference does not match " + TypeName(type));
            return resolved;
        }
        if (type.IsEnum)
        {
            object enumValue = value.ValueKind == JsonValueKind.String
                ? Enum.Parse(type, value.GetString()!, false)
                : Enum.ToObject(type, ConvertValue(session, value, Enum.GetUnderlyingType(type), depth + 1)!);
            if (!Enum.IsDefined(type, enumValue) && !ValidFlags(type, enumValue))
                throw new ArgumentException("Value is not a declared member of " + TypeName(type));
            return enumValue;
        }
        if (type == typeof(string))
            return value.ValueKind == JsonValueKind.String ? value.GetString() : throw new ArgumentException("Expected a JSON string.");
        if (type == typeof(char))
        {
            string? text = value.ValueKind == JsonValueKind.String ? value.GetString() : null;
            return text?.Length == 1 ? text[0] : throw new ArgumentException("Expected a single character.");
        }
        if (type == typeof(bool))
            return value.GetBoolean();
        if (type == typeof(byte)) return value.GetByte();
        if (type == typeof(sbyte)) return value.GetSByte();
        if (type == typeof(short)) return value.GetInt16();
        if (type == typeof(ushort)) return value.GetUInt16();
        if (type == typeof(int)) return value.GetInt32();
        if (type == typeof(uint)) return value.GetUInt32();
        if (type == typeof(long)) return value.GetInt64();
        if (type == typeof(ulong)) return value.GetUInt64();
        if (type == typeof(decimal)) return value.GetDecimal();
        if (type == typeof(double))
        {
            double number = value.GetDouble();
            return double.IsFinite(number) ? number : throw new ArgumentException("Number must be finite.");
        }
        if (type == typeof(float))
        {
            float number = value.GetSingle();
            return float.IsFinite(number) ? number : throw new ArgumentException("Number must be finite.");
        }
        Type? element = CollectionElement(type);
        if (element is not null && value.ValueKind == JsonValueKind.Array)
        {
            if (value.GetArrayLength() > 4096)
                throw new ArgumentException("Argument arrays are limited to 4096 items.");
            Array array = Array.CreateInstance(element, value.GetArrayLength());
            int index = 0;
            foreach (JsonElement item in value.EnumerateArray())
                array.SetValue(ConvertValue(session, item, element, depth + 1), index++);
            if (type.IsAssignableFrom(array.GetType()))
                return array;
            Type listType = typeof(List<>).MakeGenericType(element);
            IList list = (IList)Activator.CreateInstance(listType)!;
            foreach (object? item in array)
                list.Add(item);
            if (type.IsAssignableFrom(listType))
                return list;
            if (type.IsGenericType && type.GetGenericTypeDefinition() == typeof(HashSet<>))
                return Activator.CreateInstance(type, list);
            throw new NotSupportedException("This collection argument requires an existing session reference.");
        }
        if (IsDataStruct(type) && value.ValueKind == JsonValueKind.Object)
        {
            object result = Activator.CreateInstance(type)!;
            foreach (JsonProperty property in value.EnumerateObject())
            {
                MemberInfo slot = Slot(type, property.Name);
                if (!CanWrite(slot) || IsStatic(slot))
                    throw new ArgumentException("Struct field is not publicly writable: " + property.Name);
                WriteSlot(slot, result, ConvertValue(session, property.Value, SlotType(slot), depth + 1));
            }
            return result;
        }
        throw new ArgumentException("Expected a typed scalar, VSM data object, or compatible session $ref for " + TypeName(type));
    }

    private static bool ValidFlags(Type type, object value)
    {
        if (!type.IsDefined(typeof(FlagsAttribute), false))
            return false;
        static ulong Bits(object item)
        {
            try { return Convert.ToUInt64(item, CultureInfo.InvariantCulture); }
            catch (OverflowException) { return unchecked((ulong)Convert.ToInt64(item, CultureInfo.InvariantCulture)); }
        }
        ulong known = 0;
        foreach (object member in Enum.GetValues(type))
            known |= Bits(member);
        return (Bits(value) & ~known) == 0;
    }

    private static MemberInfo Slot(Type type, string name)
    {
        RequireNative(type);
        PropertyInfo? property = Properties(type).SingleOrDefault(candidate => candidate.Name == name);
        if (property is not null)
            return property;
        return Fields(type).SingleOrDefault(candidate => candidate.Name == name)
            ?? throw new MissingMemberException("No permitted public member named " + name);
    }

    private static IEnumerable<PropertyInfo> Properties(Type type) => type.GetProperties(PublicMembers).Where(SafeProperty)
        .OrderBy(member => DeclarationDistance(type, member.DeclaringType!)).GroupBy(member => member.Name).Select(group => group.First());
    private static IEnumerable<FieldInfo> Fields(Type type) => type.GetFields(PublicMembers).Where(SafeField)
        .OrderBy(member => DeclarationDistance(type, member.DeclaringType!)).GroupBy(member => member.Name).Select(group => group.First());
    private static IEnumerable<MethodInfo> Methods(Type type) => type.GetMethods(BindingFlags.Public | BindingFlags.Instance).Where(SafeMethod)
        .OrderBy(member => DeclarationDistance(type, member.DeclaringType!)).GroupBy(MemberId).Select(group => group.First());
    private static int DeclarationDistance(Type type, Type declaringType)
    {
        int distance = 0;
        for (Type? current = type; current is not null; current = current.BaseType, distance++)
            if (current == declaringType)
                return distance;
        return int.MaxValue;
    }

    private static Type SlotType(MemberInfo member) => member is PropertyInfo property ? property.PropertyType : ((FieldInfo)member).FieldType;
    private static bool CanRead(MemberInfo member) => member is not PropertyInfo property || property.GetMethod?.IsPublic == true;
    private static bool CanWrite(MemberInfo member) => member.Name != "IsFrozen" && (member is PropertyInfo property
        ? property.SetMethod?.IsPublic == true : member is FieldInfo { IsInitOnly: false, IsLiteral: false });
    private static bool IsStatic(MemberInfo member) => member is PropertyInfo property
        ? (property.GetMethod ?? property.SetMethod)!.IsStatic : ((FieldInfo)member).IsStatic;
    private static object? ReadSlot(MemberInfo member, object target) => member is PropertyInfo property
        ? property.GetMethod?.IsPublic == true ? property.GetValue(IsStatic(member) ? null : target) : throw new InvalidOperationException("Member is write-only.")
        : ((FieldInfo)member).GetValue(IsStatic(member) ? null : target);
    private static void WriteSlot(MemberInfo member, object target, object? value)
    {
        if (member is PropertyInfo property)
            property.SetValue(IsStatic(member) ? null : target, value);
        else
            ((FieldInfo)member).SetValue(IsStatic(member) ? null : target, value);
    }

    private static bool NativeType(Type type) => NativeTypeExclusion(type) is null;
    private static string? NativeTypeExclusion(Type type)
    {
        if (type.Assembly != NativeAssembly)
            return "outside_installed_assembly";
        if (type.Namespace != NativeNamespace)
            return "outside_vsm_namespace";
        if (!type.IsVisible)
            return "type_not_public";
        if (type.ContainsGenericParameters)
            return "open_generic_type";
        if (type.IsByRefLike || type.IsPointer || type.IsFunctionPointer)
            return "pointer_or_stack_only_type";
        if (typeof(Delegate).IsAssignableFrom(type))
            return "callbacks_and_delegates_not_exposed";
        if (type == typeof(WIVSMSequenceManager) || type.Name == "WVSMModuleIF")
            return "host_owned_lifecycle_type";
        return RestrictedNameReason(type.Name);
    }

    private static void RequireNative(Type type)
    {
        if (CatalogTypeExclusion(type) is not null)
            throw new NotSupportedException("Only safe public Yamaha.VOCALOID.VSM objects are exposed.");
    }
    private static string? RestrictedNameReason(string name)
    {
        string? word = ForbiddenNames.FirstOrDefault(word => name.Contains(word, StringComparison.OrdinalIgnoreCase));
        return word is null ? null : "restricted_name:" + word;
    }

    private static bool SafeProperty(PropertyInfo property) => PropertyExclusion(property) is null;
    private static string? PropertyExclusion(PropertyInfo property)
    {
        string? reason = property.DeclaringType is null ? "missing_declaring_type" : CatalogTypeExclusion(property.DeclaringType);
        if (reason is not null)
            return reason;
        if (property.GetMethod?.IsPublic != true && property.SetMethod?.IsPublic != true)
            return "member_not_public";
        if (property.GetIndexParameters().Length != 0)
            return "indexed_property_not_exposed";
        if (RestrictedNameReason(property.Name) is string restricted)
            return restricted;
        if (!SafeType(property.PropertyType))
            return "unsupported_property_type:" + TypeName(property.PropertyType);
        return IsStatic(property) && property.GetMethod?.IsPublic != true ? "static_write_not_exposed" : null;
    }

    private static bool SafeField(FieldInfo field) => FieldExclusion(field) is null;
    private static string? FieldExclusion(FieldInfo field)
    {
        string? reason = field.DeclaringType is null ? "missing_declaring_type" : CatalogTypeExclusion(field.DeclaringType);
        if (reason is not null)
            return reason;
        if (!field.IsPublic)
            return "member_not_public";
        if (RestrictedNameReason(field.Name) is string restricted)
            return restricted;
        return SafeType(field.FieldType) ? null : "unsupported_field_type:" + TypeName(field.FieldType);
    }

    private static bool SafeMethod(MethodInfo method) => MethodExclusion(method) is null;
    private static string? MethodExclusion(MethodInfo method)
    {
        string? reason = method.DeclaringType is null ? "missing_declaring_type" : CatalogTypeExclusion(method.DeclaringType);
        if (reason is not null)
            return reason;
        if (!method.IsPublic)
            return "member_not_public";
        if (method.IsStatic)
            return "static_method_not_exposed";
        if (method.IsSpecialName)
            return "accessor_or_special_method_use_property_api";
        if (method.ContainsGenericParameters)
            return "open_generic_method";
        if ((method.CallingConvention & CallingConventions.VarArgs) != 0)
            return "varargs_not_exposed";
        if (method.Name is "GetType" or "GetHashCode" or "Equals" or "ToString" or "MemberwiseClone" or "Finalize")
            return "runtime_object_method_not_exposed";
        if (RestrictedNameReason(method.Name) is string restricted)
            return restricted;
        string? operation = ForbiddenOperations.FirstOrDefault(prefix => method.Name.StartsWith(prefix, StringComparison.OrdinalIgnoreCase));
        if (operation is not null && !ReviewedDataMethod(method))
            return "host_owned_operation:" + operation;
        if (!SafeType(method.ReturnType))
            return "unsupported_return_type:" + TypeName(method.ReturnType);
        return ParameterExclusion(method);
    }

    private static bool SafeConstructor(ConstructorInfo constructor) => ConstructorExclusion(constructor) is null;
    private static string? ConstructorExclusion(ConstructorInfo constructor)
    {
        string? reason = constructor.DeclaringType is null ? "missing_declaring_type" : CatalogTypeExclusion(constructor.DeclaringType);
        if (reason is not null)
            return reason;
        if (!constructor.IsPublic)
            return "member_not_public";
        if (constructor.IsStatic || !IsDataStruct(constructor.DeclaringType!))
            return "native_wrapper_construction_owned_by_host";
        return ParameterExclusion(constructor);
    }

    private static string? ParameterExclusion(MethodBase method)
    {
        ParameterInfo? parameter = method.GetParameters().FirstOrDefault(parameter => !SafeParameter(parameter));
        return parameter is null ? null : (parameter.ParameterType.IsByRef ? "unsupported_byref_parameter:" : "unsupported_parameter:") +
            parameter.Position + ":" + parameter.Name + ":" + TypeName(parameter.ParameterType);
    }

    private static bool ReviewedDataMethod(MethodInfo method) => method.DeclaringType == typeof(WIVSMMidiPart) &&
        method.Name == "RenderableNoteDuration" && method.ReturnType == typeof(int) &&
        method.GetParameters() is [ParameterInfo parameter] && parameter.ParameterType == typeof(int);

    private static bool IsScalar(Type type) => type == typeof(string) || type == typeof(char) || type == typeof(bool) ||
        type == typeof(byte) || type == typeof(sbyte) || type == typeof(short) || type == typeof(ushort) || type == typeof(int) ||
        type == typeof(uint) || type == typeof(long) || type == typeof(ulong) || type == typeof(float) || type == typeof(double) || type == typeof(decimal);
    private static bool SafeType(Type type, int depth = 0)
    {
        if (depth > 12 || type.IsPointer || type.IsFunctionPointer || type.IsByRef || type == typeof(nint) || type == typeof(nuint))
            return false;
        if (type == typeof(void) || IsScalar(type))
            return true;
        if (Nullable.GetUnderlyingType(type) is Type nullable)
            return SafeType(nullable, depth + 1);
        if (NativeType(type))
            return !type.IsValueType || type.IsEnum || IsDataStruct(type, depth + 1);
        return CollectionElement(type, depth + 1) is not null;
    }

    private static bool IsDataStruct(Type type, int depth = 0) => depth <= 12 && NativeType(type) && type.IsValueType && !type.IsEnum &&
        type.GetFields(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance).All(field =>
            IsScalar(field.FieldType) || (field.FieldType.IsValueType && SafeType(field.FieldType, depth + 1)));

    private static Type? CollectionElement(Type type, int depth = 0)
    {
        if (depth > 12 || type == typeof(string))
            return null;
        if (type.IsArray)
            return type.GetArrayRank() == 1 && SafeType(type.GetElementType()!, depth + 1) ? type.GetElementType() : null;
        foreach (Type contract in type.GetInterfaces().Prepend(type))
        {
            if (!contract.IsGenericType)
                continue;
            Type definition = contract.GetGenericTypeDefinition();
            if (definition != typeof(IEnumerable<>) && definition != typeof(IEnumerator<>))
                continue;
            Type element = contract.GetGenericArguments()[0];
            if (SafeType(element, depth + 1))
                return element;
        }
        return null;
    }

    private static bool HasCount(object value) => value is ICollection || value.GetType().GetInterfaces().Any(type =>
        type.IsGenericType && (type.GetGenericTypeDefinition() == typeof(ICollection<>) || type.GetGenericTypeDefinition() == typeof(IReadOnlyCollection<>)));
    private static int Count(object value)
    {
        if (value is ICollection collection)
            return collection.Count;
        Type contract = value.GetType().GetInterfaces().First(type => type.IsGenericType &&
            (type.GetGenericTypeDefinition() == typeof(ICollection<>) || type.GetGenericTypeDefinition() == typeof(IReadOnlyCollection<>)));
        return (int)contract.GetProperty("Count")!.GetValue(value)!;
    }
    private static bool IsReadOnly(string name) => new[] { "Get", "Can", "Has", "Is", "Contains", "IndexOf" }.Any(prefix => name.StartsWith(prefix, StringComparison.Ordinal));
    private static bool InvalidatesChildren(string name) => new[] { "Remove", "Delete", "Clear", "Replace", "Reset", "Rollback", "Undo", "Redo" }.Any(prefix => name.StartsWith(prefix, StringComparison.Ordinal));
    private static string TypeName(Type type) => type.FullName ?? type.Name;
    private static string MemberId(MethodBase method) => method.Name + "(" + string.Join(",", method.GetParameters().Select(parameter => TypeName(parameter.ParameterType))) + ")";
    private static object DescribeMethod(MethodBase method) => new
    {
        member_id = MemberId(method),
        return_type = method is MethodInfo info ? TypeName(info.ReturnType) : TypeName(method.DeclaringType!),
        parameters = method.GetParameters().Select(DescribeParameter).ToArray(),
        supported = method.GetParameters().All(SafeParameter)
    };

    private static object DescribeParameter(ParameterInfo parameter) => new
    {
        name = parameter.Name,
        type = TypeName(parameter.ParameterType),
        value_type = TypeName(ParameterValueType(parameter)),
        direction = parameter.ParameterType.IsByRef ? parameter.IsOut && !parameter.IsIn ? "out" : parameter.IsIn && !parameter.IsOut ? "in" : "ref" : "in",
        optional = parameter.IsOptional
    };

    private static JsonElement Required(JsonElement value, string name) => value.TryGetProperty(name, out JsonElement result)
        ? result : throw new ArgumentException("Missing parameter: " + name);
    private static string RequiredString(JsonElement value, string name) => Required(value, name).ValueKind == JsonValueKind.String
        ? Required(value, name).GetString()! : throw new ArgumentException(name + " must be a string.");
    private static string? OptionalString(JsonElement value, string name) => !value.TryGetProperty(name, out JsonElement result) || result.ValueKind == JsonValueKind.Null
        ? null : result.ValueKind == JsonValueKind.String ? result.GetString() : throw new ArgumentException(name + " must be a string.");
    private static int Integer(JsonElement value, string name, int fallback) => value.TryGetProperty(name, out JsonElement result) ? result.GetInt32() : fallback;
    private static ulong Unsigned(JsonElement value, string name, ulong fallback) => value.TryGetProperty(name, out JsonElement result) ? result.GetUInt64() : fallback;
    private static double Number(JsonElement value, string name, double fallback) => value.TryGetProperty(name, out JsonElement result) ? result.GetDouble() : fallback;
    private static bool Boolean(JsonElement value, string name, bool fallback) => value.TryGetProperty(name, out JsonElement result) ? result.GetBoolean() : fallback;
    private static JsonElement[] Arguments(JsonElement value)
    {
        if (!value.TryGetProperty("args", out JsonElement arguments))
            return [];
        if (arguments.ValueKind != JsonValueKind.Array)
            throw new ArgumentException("args must be an array.");
        return arguments.EnumerateArray().ToArray();
    }

    private static void ValidateObjectKeys(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Object)
        {
            HashSet<string> names = new(StringComparer.Ordinal);
            foreach (JsonProperty property in value.EnumerateObject())
            {
                if (!names.Add(property.Name))
                    throw new ArgumentException("Duplicate JSON object property: " + property.Name);
                ValidateObjectKeys(property.Value);
            }
        }
        else if (value.ValueKind == JsonValueKind.Array)
            foreach (JsonElement item in value.EnumerateArray())
                ValidateObjectKeys(item);
    }

    private static (string? Line, bool TooLong) ReadLine(TextReader input)
    {
        StringBuilder line = new();
        bool tooLong = false;
        int character;
        while ((character = input.Read()) != -1 && character != '\n')
        {
            if (line.Length < MaxLineLength)
                line.Append((char)character);
            else
                tooLong = true;
        }
        if (character == -1 && line.Length == 0 && !tooLong)
            return (null, false);
        if (line.Length > 0 && line[^1] == '\r')
            line.Length--;
        return (line.ToString(), tooLong);
    }
}
