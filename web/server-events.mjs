export function createEventJournal({limit = 10_000} = {}) {
  const maxEntries = Number.isInteger(limit) && limit > 0 ? limit : 10_000;
  const events = [];
  const activeRuns = new Map();
  let nextId = 1;

  function publish(event, context = {}) {
    const runId = event.run_id ?? event.turn_id ?? context.runId ?? null;
    const published = {
      ...event,
      event_id: event.event_id ?? `evt-${nextId++}`,
      timestamp: event.timestamp ?? Date.now(),
      session_id: event.session_id ?? context.sessionId ?? null,
      run_id: runId,
    };
    events.push(published);
    if (events.length > maxEntries) events.splice(0, events.length - maxEntries);
    updateActiveRun(published);
    return published;
  }

  function replayAfter(lastEventId) {
    if (!lastEventId) return [];
    const index = events.findIndex((event) => event.event_id === lastEventId);
    return index === -1 ? null : events.slice(index + 1);
  }

  function clearRun(runId) {
    activeRuns.delete(runId);
  }

  function activeSnapshots() {
    return [...activeRuns.values()].map((event) => ({...event}));
  }

  function updateActiveRun(event) {
    if (!event.run_id) return;
    if (event.type === 'run_started' || event.type === 'approval_required') {
      activeRuns.set(event.run_id, {...event});
      return;
    }
    if (['done', 'error', 'run_stopped'].includes(event.type)) {
      if (event.type === 'done' && activeRuns.get(event.run_id)?.type === 'approval_required' && !event.approval_finalized) return;
      activeRuns.delete(event.run_id);
      return;
    }
    const active = activeRuns.get(event.run_id);
    if (!active) return;
    activeRuns.set(event.run_id, {
      ...active,
      stage: event.stage ?? active.stage,
      stage_group: event.stage_group ?? active.stage_group,
      label: event.label ?? active.label,
      raw_stage: event.raw_stage ?? active.raw_stage,
      timestamp: event.timestamp,
    });
  }

  return {publish, replayAfter, clearRun, activeSnapshots};
}
