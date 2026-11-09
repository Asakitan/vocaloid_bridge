"""Actual MCP half-open pitch-clear boundary and native history regression."""
import sys
import verify_features as v


@v.feature('score.pitch_clear_boundaries', 'score', 'score_compose', 'project_edit', 'project_save', 'project_open')
async def pitch_clear_boundaries(check):
    seed = await check.call('score_compose', output_name=check.output('pitch-clear-seed'),
                            title='Pitch clear boundaries', bpm=120,
                            notes=[{'start': 0, 'duration': 2, 'pitch': 60,
                                    'lyric': 'あ', 'phoneme': 'a', 'lang_id': 0}])
    sid = seed['native_session']['session_id']
    scope = {'track_index': 0, 'part_index': 0, 'note_index': 0}
    try:
        async def points():
            return (await check.edit(sid, 'pitch.list', **scope))['points']

        await check.edit(sid, 'pitch.set', **scope, replace=True,
                         points=[{'tick': 100, 'value': 63}, {'tick': 400, 'value': 64}])
        baseline = await points()
        v.require([p['tick'] for p in baseline] == [100, 400], 'Unexpected seed pitch points', baseline)
        await check.edit(sid, 'pitch.clear', **scope, begin_tick=100, end_tick=400)
        v.require([p['tick'] for p in await points()] == [400], 'Exclusive end boundary was removed')
        await check.edit(sid, 'undo')
        v.require(await points() == baseline, 'Clear undo did not restore both boundary points')
        await check.edit(sid, 'redo')
        v.require([p['tick'] for p in await points()] == [400], 'Clear redo lost the exclusive endpoint')
        await check.edit(sid, 'undo')
        history = await check.edit(sid, 'history.status')
        await check.rejected('project_edit', 'end_tick|range', session_id=sid, operation='pitch.clear',
                             options={**scope, 'begin_tick': 400, 'end_tick': 400})
        v.require(await points() == baseline and await check.edit(sid, 'history.status') == history,
                  'Invalid interval changed the curve or history')
        await check.edit(sid, 'pitch.clear', **scope, begin_tick=99, end_tick=100)
        v.require(await points() == baseline and await check.edit(sid, 'history.status') == history,
                  'Empty half-open interval changed the curve or history')
        await check.edit(sid, 'pitch.clear', **scope, begin_tick=100, end_tick=101)
        v.require([p['tick'] for p in await points()] == [400], 'Single-tick clear missed its point')
        await check.edit(sid, 'undo')
        await check.edit(sid, 'pitch.clear', **scope, begin_tick=400, end_tick=401)
        v.require([p['tick'] for p in await points()] == [100], 'Single-tick clear changed the wrong point')
        _, path = await check.save(sid, 'pitch-clear-boundary')
        reopened = (await check.call('project_open', path=str(path)))['session_id']
        try:
            v.require([p['tick'] for p in (await check.edit(reopened, 'pitch.list', **scope))['points']] == [100],
                      'Saved half-open pitch curve differs after reopen')
        finally:
            await check.close(reopened)
        await check.edit(sid, 'pitch.clear', **scope)
        v.require(await points() == [], 'Full clear left direct-pitch data')
        await check.edit(sid, 'undo')
        v.require([p['tick'] for p in await points()] == [100], 'Full clear undo failed')
    finally:
        await check.close(sid)


if __name__ == '__main__':
    if '--case' not in sys.argv:
        sys.argv.extend(['--case', 'score.pitch_clear_boundaries'])
    raise SystemExit(v.main())
