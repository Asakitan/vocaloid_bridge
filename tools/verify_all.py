"""Run the MCP acceptance and maintained native operation cases."""
import verify_features as v
import check_library_remaining
import check_audio_remaining
import check_score_remaining_mcp
import check_session_features
import check_voicecolor_audio
import check_transport
import check_project_preservation
import check_track_freeze
import check_midi_recording_case
import check_clipboard_extension_guard
import check_archive_transfer
import check_clipboard_extended_cut
import check_archive_merge

baseline_ids = {case.identifier for case in v.CASES}
import check_interchange_remaining

# Experimental format probes remain individually callable, not release gates.
release_interchange = {"remaining.clone_audio", "remaining.vsqx3", "remaining.vsqx4", "remaining.ppsf3",
                       "remaining.integrity_guard", "remaining.integrity_ai", "remaining.ppsf3_selected_voice"}
v.CASES[:] = [case for case in v.CASES if case.identifier in baseline_ids | release_interchange]

if __name__ == "__main__":
    raise SystemExit(v.main())
