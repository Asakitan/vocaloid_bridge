$ErrorActionPreference = 'Stop'
$source = @'
#nullable enable
global using System;
global using System.Collections.Generic;
global using System.Linq;
'@ + "`n" + (Get-Content -Raw -Encoding UTF8 "$PSScriptRoot/../native/ProjectArchiveArrays.cs") + @'

public static class TempoArrayHelperProbe {
    static System.Text.Json.Nodes.JsonArray Parse(string json) => (System.Text.Json.Nodes.JsonArray)System.Text.Json.Nodes.JsonNode.Parse(json)!;
    public static void Run() {
        var start = Parse("[{\"pos\":0,\"value\":12000,\"x\":\"keep\"},{\"pos\":480,\"value\":13000,\"x\":\"move\"}]");
        var original = ProjectArchiveArrays.ReadTempo(start, true);
        var moved = ProjectArchiveArrays.TempoTransition(original, Parse("[{\"pos\":0,\"value\":12000},{\"pos\":960,\"value\":14000}]"), 480, 960, 14000);
        var output = Parse("[{\"pos\":960,\"value\":14000},{\"pos\":0,\"value\":12000}]");
        ProjectArchiveArrays.OverlayTempo(output, moved);
        if ((string?)output[0]!["x"] != "move" || (int)output[0]!["value"]! != 14000) throw new Exception("move overlay");
        var removed = ProjectArchiveArrays.TempoTransition(moved, Parse("[{\"pos\":0,\"value\":12000}]"), 960, null, null);
        var recreated = ProjectArchiveArrays.TempoTransition(removed, Parse("[{\"pos\":0,\"value\":12000},{\"pos\":960,\"value\":14000}]"), null, 960, 14000);
        if (recreated[960].Extra.Count != 0 || (string?)original[480].Extra["x"] != "move") throw new Exception("delete or snapshot isolation");
        try { ProjectArchiveArrays.ReadTempo(Parse("[{\"pos\":0,\"value\":1},{\"pos\":0,\"value\":1}]"), true); throw new Exception("duplicate accepted"); }
        catch (System.IO.InvalidDataException) { }
        try { ProjectArchiveArrays.TempoTransition(moved, Parse("[{\"pos\":0,\"value\":12000}]"), null, 960, 14000); throw new Exception("collision accepted"); }
        catch (System.IO.InvalidDataException) { }
    }
}
'@
Add-Type -TypeDefinition $source
[TempoArrayHelperProbe]::Run()
Write-Output 'tempo helper synthetic probe passed'
