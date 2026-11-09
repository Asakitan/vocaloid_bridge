"""Run the original MCP acceptance plus the maintained session-06 operation cases."""
import verify_features as v
import check_library_remaining
import check_audio_remaining
import check_score_remaining_mcp

baseline_ids = {case.identifier for case in v.CASES}
import check_interchange_remaining

# Experimental format probes remain individually callable, not release gates.
release_interchange = {"remaining.clone_audio", "remaining.vsqx3", "remaining.vsqx4", "remaining.ppsf3"}
v.CASES[:] = [case for case in v.CASES if case.identifier in baseline_ids | release_interchange]

if __name__ == "__main__":
    raise SystemExit(v.main())
