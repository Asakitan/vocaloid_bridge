#if VOCALOID7
using System.IO;

// VOCALOID7 removed the managed VMM media model. Keep the shared library
// dispatch compilable and fail closed for the operations that depended on it.
internal sealed partial class EngineHost
{
    private int mediaAccessDepth;

    private static void InvalidateMediaCatalog()
    {
        throw new NotSupportedException("VOCALOID7 has no MediaManager catalog to invalidate.");
    }
}

internal static class MediaPropertyWorker
{
    internal static int Run(string workspace, string token) =>
        throw new NotSupportedException(
            "VOCALOID7 does not expose the managed MediaManager API, so staged media property editing is unavailable.");
}
#endif
