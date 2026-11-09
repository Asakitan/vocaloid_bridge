"""Native audio effect history and failed-mutation regression."""
import sys
import verify_features as v


@v.feature('audio.effect_history', 'audio', 'project_audio', 'project_edit', 'project_save', 'project_open')
async def effect_history(check):
    async with check.project() as sid:
        async def effects():
            return (await check.audio(sid, 'effects', scope='master'))['effects']

        catalog = (await check.audio(sid, 'effects', scope='catalog'))['effects']
        gain = next(item for item in catalog if item['name'].casefold() == 'gain')
        delay = next(item for item in catalog if item['name'].casefold() == 'delay')
        meta = await check.audio(sid, 'effects', scope='catalog', effect_id=gain['effect_id'])
        parameter = meta['parameters'][0]['name']
        v.require(await effects() == [], 'Fixture master effect chain is not empty')
        await check.audio(sid, 'set_effect', action='add', effect_id=gain['effect_id'])
        added = await effects()
        v.require(len(added) == 1, 'Add readback failed')
        await check.edit(sid, 'undo')
        v.require(await effects() == [], 'Undo did not remove the added effect')
        await check.edit(sid, 'redo')
        v.require(await effects() == added, 'Redo did not restore the added effect')

        await check.audio(sid, 'set_effect', action='set', slot=0,
                          parameters={parameter: 0.25}, bypass=True)
        updated = await effects()
        v.require(updated[0]['bypass'] and updated != added, 'Set readback failed')
        await check.edit(sid, 'undo')
        v.require(await effects() == added, 'Undo did not restore original effect state')
        await check.edit(sid, 'redo')
        v.require(await effects() == updated, 'Redo did not restore updated effect state')

        before = await effects()
        history = await check.edit(sid, 'history.status')
        await check.rejected('project_audio', 'preset', session_id=sid, operation='set_effect',
                             options={'action': 'set', 'slot': 0, 'preset': '__missing_preset__'})
        v.require(await effects() == before and await check.edit(sid, 'history.status') == history,
                  'Failed effect edit changed chain or history')
        await check.audio(sid, 'set_effect', action='add', effect_id=delay['effect_id'])
        ordered = await effects()
        await check.audio(sid, 'set_effect', action='move', slot=1, target_slot=0)
        moved = await effects()
        v.require([x['effect_id'] for x in moved] == [delay['effect_id'], gain['effect_id']], 'Move readback failed')
        await check.edit(sid, 'undo')
        v.require(await effects() == ordered, 'Undo did not restore effect order')
        await check.edit(sid, 'redo')
        v.require(await effects() == moved, 'Redo did not restore moved order')
        await check.audio(sid, 'set_effect', action='remove', slot=0)
        removed = await effects()
        v.require(len(removed) == 1 and removed[0]['effect_id'] == gain['effect_id'], 'Remove readback failed')
        await check.edit(sid, 'undo')
        v.require(await effects() == moved, 'Undo did not restore removed effect')
        await check.edit(sid, 'redo')
        v.require(await effects() == removed, 'Redo did not remove effect again')
        _, path = await check.save(sid, 'effect-history')
        reopened = (await check.call('project_open', path=str(path)))['session_id']
        try:
            actual = (await check.audio(reopened, 'effects', scope='master'))['effects']
            v.require(actual == removed, 'Reopened effect chain differs')
        finally:
            await check.close(reopened)


if __name__ == '__main__':
    if '--case' not in sys.argv:
        sys.argv.extend(['--case', 'audio.effect_history'])
    raise SystemExit(v.main())
