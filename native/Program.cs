using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Runtime.Loader;
using System.Text;
using System.Text.Json;
using Yamaha.VOCALOID.VSM;

internal static class Program
{
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern nint AddDllDirectory(string directory);

    [DllImport("kernel32", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetDefaultDllDirectories(uint flags);

    [DllImport("user32")]
    private static extern nint GetForegroundWindow();

    [DllImport("kernel32")]
    private static extern uint GetCurrentThreadId();

    [DllImport("user32", SetLastError = true)]
    private static extern nint GetThreadDesktop(uint threadId);

    [DllImport("user32", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetUserObjectInformation(nint handle, int index, nint buffer, uint length, out uint needed);

    [STAThread]
    private static int Main(string[] arguments)
    {
        try
        {
            bool serve = arguments.Length == 3 && arguments[0] == "--serve";
            bool mediaProperty = arguments.Length == 4 && arguments[0] == "--media-property";
            bool probe = arguments.Length == 2 || (arguments.Length == 3 && arguments[0] == "--probe");
            if (!serve && !probe && !mediaProperty)
                throw new ArgumentException("Expected --serve INSTALL WORKSPACE or --probe INSTALL OUTPUT.");
            int offset = arguments.Length >= 3 ? 1 : 0;
            string install = Path.GetFullPath(arguments[offset]);
            string output = Path.GetFullPath(arguments[offset + 1]);
            string desktop = DesktopName();
            if (string.Equals(desktop, "Default", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(desktop, "Winlogon", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(desktop, "Disconnect", StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Native engine startup requires the private-desktop launcher.");
            if (!SetDefaultDllDirectories(0x0c00) || AddDllDirectory(install) == nint.Zero)
                throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            AssemblyLoadContext.Default.Resolving += (_, name) =>
            {
                if (string.IsNullOrEmpty(name.Name) || Path.GetFileName(name.Name) != name.Name)
                    return null;
                string path = Path.Combine(install, name.Name + ".dll");
                return File.Exists(path) ? AssemblyLoadContext.Default.LoadFromAssemblyPath(path) : null;
            };
            AssemblyName core = CoreReference();
            string corePath = Path.Combine(install, core.Name + ".dll");
            if (!File.Exists(corePath))
                throw new FileNotFoundException(
                    $"The host was built for {core.Name}, but that assembly is missing from {install}.", corePath);
            Assembly assembly = AssemblyLoadContext.Default.LoadFromAssemblyPath(corePath);
            NativeLibrary.SetDllImportResolver(assembly, (name, _, _) =>
            {
                if (Path.GetFileName(name) != name)
                    return nint.Zero;
                string path = Path.Combine(install, name.EndsWith(".dll", StringComparison.OrdinalIgnoreCase) ? name : name + ".dll");
                return File.Exists(path) ? NativeLibrary.Load(path) : nint.Zero;
            });
            if (mediaProperty)
                return StageMediaProperty(output, arguments[3]);
            if (!serve)
                return Probe(output);
            using StreamReader input = new(Console.OpenStandardInput(), new UTF8Encoding(false, true), false, 4096);
            using StreamWriter writer = new(Console.OpenStandardOutput(), new UTF8Encoding(false), 4096) { AutoFlush = true };
            Console.SetOut(Console.Error);
            return Serve(output, install, desktop, input, writer);
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(JsonSerializer.Serialize(new { error = new { type = error.GetType().Name, message = error.Message } }));
            return 1;
        }
    }

    private static AssemblyName CoreReference() =>
        typeof(Program).Assembly.GetReferencedAssemblies().FirstOrDefault(name =>
            name.Name is not null && name.Name.StartsWith("VOCALOID", StringComparison.OrdinalIgnoreCase))
        ?? throw new InvalidOperationException("The host was not built against a VOCALOID core assembly.");

    private static string DesktopName()
    {
        nint desktop = GetThreadDesktop(GetCurrentThreadId());
        if (desktop == nint.Zero)
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
        GetUserObjectInformation(desktop, 2, nint.Zero, 0, out uint needed);
        if (needed < 2 || needed > 65536)
            throw new InvalidOperationException("Unable to read the thread desktop name.");
        nint buffer = Marshal.AllocHGlobal(checked((int)needed));
        try
        {
            if (!GetUserObjectInformation(desktop, 2, buffer, needed, out _))
                throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            return Marshal.PtrToStringUni(buffer) ?? throw new InvalidOperationException("Empty thread desktop name.");
        }
        finally { Marshal.FreeHGlobal(buffer); }
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static int StageMediaProperty(string workspace, string stage) => MediaPropertyWorker.Run(workspace, stage);

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static int Serve(string workspace, string install, string desktop, TextReader input, TextWriter output)
    {
        using EngineHost host = new(workspace, install);
        return new RpcServer(host, desktop).Run(input, output);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static int Probe(string output)
    {
        nint foreground = GetForegroundWindow();
        using WIVSMSequenceManager manager = WVSMModuleIF.CreateManager(EngineHost.EngineProduct, EngineHost.EngineVersion)
            ?? throw new InvalidOperationException("VSM manager creation failed: " + WVSMModuleIF.LastError());
        VSMSequenceData settings = EngineHost.SequenceSettings(VSMSamplingRate._44100);
        WIVSMSequence sequence = manager.CreateSequence(settings)
            ?? throw new InvalidOperationException("VSM sequence creation failed: " + manager.LastError);
        sequence.Title = "Background Native Probe";
        if (sequence.InsertTimeSig(0, new VSMTimeSigEvent(4, 4)) is null ||
            sequence.InsertTempo(VSMRelTick.Zero, WIVSMTempo.DefaultValue) is null ||
            !sequence.Commit(false))
            throw new InvalidOperationException("VSM initialization failed: " + sequence.LastError);
        string stage = Path.Combine(output, "native-probe-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(stage);
        if (!sequence.Save(stage, false))
            throw new InvalidOperationException("VSM save failed: " + sequence.LastError);
        string project = Path.Combine(stage, "Project");
        string archive = Path.Combine(output, "native-probe-" + Guid.NewGuid().ToString("N") + ".vpr");
        ZipFile.CreateFromDirectory(project, archive, CompressionLevel.NoCompression, true);
        sequence.Close();
        bool closed = !sequence.IsOpen;
        WIVSMSequence reopened = manager.OpenSequence(Path.Combine(project, "sequence.json"), project, settings)
            ?? throw new InvalidOperationException("VSM reopen failed: " + manager.LastError);
        string title = reopened.Title;
        ulong nativeTracks = reopened.NumTrack;
        reopened.Close();
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            created = true,
            saved = File.Exists(archive),
            closed,
            reopened_title = title,
            archive,
            foreground_unchanged = foreground == GetForegroundWindow(),
            foreground_before = foreground.ToInt64(),
            foreground_after = GetForegroundWindow().ToInt64(),
            native_tracks = nativeTracks
        }));
        return closed && foreground == GetForegroundWindow() ? 0 : 2;
    }
}
