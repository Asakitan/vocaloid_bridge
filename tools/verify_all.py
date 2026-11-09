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
import check_clipboard_resources
import check_archive_transfer
import check_clipboard_ambiguity
import check_clipboard_extended_cut
import check_archive_merge
import check_tempo_merge
import check_archive_output
import check_timesig_merge
import check_archive_audio_transfer
import check_archive_library
import check_controller_splitting
import check_archive_audio_mutations
import check_audio_effect_history
import check_archive_media_extensions
import check_archive_transport
import check_pitch_clear_boundaries
import check_metadata_history
import check_note_array_extensions
import check_tempo_metadata_noop
import check_master_automation_20
import check_track_automation_21
import check_timeline_delete_21
import check_note_delete_guards_21
import check_timeline_meter_22
import check_extension_edit_guards_22

baseline_ids = {case.identifier for case in v.CASES}
import check_interchange_remaining

# Experimental format probes and the protected extension-audio write scenario
# remain individually callable, not release gates.
release_interchange = {"remaining.clone_audio", "remaining.vsqx3", "remaining.vsqx4", "remaining.ppsf3",
                       "remaining.integrity_guard", "remaining.integrity_ai", "remaining.ppsf3_selected_voice"}
experimental = {"preservation.audio_mutation", "preservation.controller_split_native_probe",
                "preservation.controller_split_generated_probe", "preservation.metadata_native_marker_probe",
                "preservation.metadata_tempo_marker_probe", "preservation.note_pitch_array_probe",
                "preservation.note_pitch_transitions", "preservation.tempo_collision_native_probe",
                "preservation.tempo_same_collision_native_probe", "preservation.note_pitch_delete_note",
                "preservation.note_pitch_delete_clear", "preservation.note_pitch_delete_part",
                "preservation.note_pitch_delete_track", "preservation.timeline_delete_native_21"}
v.CASES[:] = [case for case in v.CASES if case.identifier in baseline_ids | release_interchange
              and case.identifier not in experimental]

if __name__ == "__main__":
    raise SystemExit(v.main())
