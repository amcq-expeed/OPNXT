import {
  ProgressUpdate,
  extractStage,
  extractProgressValue,
  buildStageTimeline,
  convertProgressToPercent,
  interpretStreamUpdates,
} from '../lib/acceleratorStream';
import {
  connectAcceleratorArtifactStream,
  type AcceleratorArtifactSnapshotEvent,
  type AcceleratorArtifactUpdatesEvent,
  type AcceleratorStreamFactory,
} from '../lib/api';

declare const describe: (name: string, fn: () => void) => void;
declare const it: (name: string, fn: () => void) => void;
declare const expect: (value: unknown) => any;
declare const beforeEach: (fn: () => void) => void;

const noop = () => {};

type MockUpdate = ProgressUpdate & { stage: string };

describe('accelerator streaming helpers', () => {
  it('extractStage returns stage from payload', () => {
    expect(extractStage({ stage: 'draft' })).toBe('draft');
    expect(extractStage({ meta: { stage: 'READY' } })).toBe('READY');
    expect(extractStage({})).toBeNull();
  });

  it('extractProgressValue reads progress from payload', () => {
    expect(extractProgressValue({ progress: 0.6 })).toBe(0.6);
    expect(extractProgressValue({ meta: { progress: 0.85 } })).toBe(0.85);
    expect(extractProgressValue({ progress: '1' })).toBeNull();
  });

  it('convertProgressToPercent handles fractional values', () => {
    expect(convertProgressToPercent(0.6)).toBe(60);
    expect(convertProgressToPercent(42)).toBe(42);
    expect(convertProgressToPercent(NaN)).toBe(0);
    expect(convertProgressToPercent(1)).toBe(100);
  });

  it('buildStageTimeline orders stages by appearance and known order', () => {
    const updates: MockUpdate[] = [
      { id: '1', message: 'starting', kind: 'info', timestamp: Date.now(), stage: 'analysis' },
      { id: '2', message: 'drafting', kind: 'info', timestamp: Date.now(), stage: 'draft' },
      { id: '3', message: 'reviewing', kind: 'info', timestamp: Date.now(), stage: 'validation' },
      { id: '4', message: 'finalizing', kind: 'success', timestamp: Date.now(), stage: 'ready' },
    ];

    const timeline = buildStageTimeline(updates, 'ready');
    expect(timeline).toEqual([
      { stage: 'analysis', label: 'Collecting context', state: 'done' },
      { stage: 'draft', label: 'Drafting deliverables', state: 'done' },
      { stage: 'validation', label: 'Validating outputs', state: 'done' },
      { stage: 'ready', label: 'Ready', state: 'active' },
    ]);
  });

  it('buildStageTimeline tolerates duplicate or unknown stages', () => {
    const updates: ProgressUpdate[] = [
      { id: 'a', message: 'drafting…', kind: 'info', timestamp: Date.now(), stage: 'draft' },
      { id: 'b', message: 'still drafting…', kind: 'info', timestamp: Date.now(), stage: 'draft' },
      { id: 'c', message: 'packaging', kind: 'info', timestamp: Date.now(), stage: 'packaging' },
      { id: 'd', message: 'ready', kind: 'success', timestamp: Date.now(), stage: 'ready' },
    ];

    const timeline = buildStageTimeline(updates, 'ready');
    expect(timeline.map((item) => item.stage)).toEqual(['draft', 'packaging', 'ready']);
    expect(timeline[0].state).toBe('done');
    expect(timeline[2]).toMatchObject({ stage: 'ready', state: 'active' });
  });

  it('interpretStreamUpdates returns structured instructions for commit workflow', () => {
    const interpretation = interpretStreamUpdates([
      { type: 'status', preview: 'Validating artifacts', stage: 'validation', progress: 0.8 },
      { type: 'draft_update', preview: 'Latest draft chunk', stage: 'draft', progress: 0.82 },
      { type: 'commit', preview: 'Draft ready for review', stage: 'ready', progress: 1 },
    ]);

    expect(interpretation.activateStream).toBe(true);
    expect(interpretation.stopStream).toBe(true);
    expect(interpretation.clearLiveDraft).toBe(true);
    expect(interpretation.openDrawer).toBe(true);
    expect(interpretation.progressEntries.map((entry) => entry.message)).toEqual([
      'Validating artifacts',
      'Drafting artifacts…',
      'Draft ready for review',
    ]);
    expect(interpretation.nextLiveDraft).toBe('Latest draft chunk');
  });

  it('interpretStreamUpdates handles error payloads and leaves stream inactive on empty input', () => {
    const interpretation = interpretStreamUpdates([
      { type: 'error', preview: 'Generation failed', stage: 'error' },
    ]);

    expect(interpretation.streamError).toBe('Generation failed');
    expect(interpretation.activateStream).toBeUndefined();
    expect(interpretation.progressEntries[0]).toMatchObject({
      message: 'Generation failed',
      kind: 'error',
      stage: 'error',
    });

    const emptyInterpretation = interpretStreamUpdates([]);
    expect(emptyInterpretation.progressEntries).toHaveLength(0);
    expect(emptyInterpretation.openDrawer).toBeUndefined();
  });

  it('interpretStreamUpdates captures timestamps from payload metadata', () => {
    const tsIso = new Date().toISOString();
    const interpretation = interpretStreamUpdates([
      { type: 'status', preview: 'Starting…', stage: 'analysis', progress: 0.1, ts: tsIso },
    ]);

    expect(interpretation.progressEntries).toHaveLength(1);
    const entry = interpretation.progressEntries[0];
    expect(entry.timestamp).toBeGreaterThan(0);
    expect(entry.timestamp).toBe(new Date(tsIso).getTime());
    expect(entry.stage).toBe('analysis');
  });
});

describe('connectAcceleratorArtifactStream', () => {
  let statuses: Array<{ status: string; attempt?: number }>;
  let snapshots: AcceleratorArtifactSnapshotEvent[];
  let updates: AcceleratorArtifactUpdatesEvent[];
  let heartbeats: number;

  beforeEach(() => {
    statuses = [];
    snapshots = [];
    updates = [];
    heartbeats = 0;
  });

  it('delivers snapshots and dedupes incremental updates by revision', () => {
    let capturedEventHandler: ((event: AcceleratorArtifactSnapshotEvent | AcceleratorArtifactUpdatesEvent | any) => void) | null = null;

    const factory: AcceleratorStreamFactory = (_sessionId, onEvent) => {
      capturedEventHandler = onEvent;
      return noop;
    };

    const disconnect = connectAcceleratorArtifactStream(
      'session-test',
      {
        onSnapshot: (event) => snapshots.push(event),
        onUpdates: (event) => updates.push(event),
        onHeartbeat: () => {
          heartbeats += 1;
        },
        onStatus: (status, meta) => {
          statuses.push({ status, attempt: meta?.attempt });
        },
      },
      {
        initialRevision: 1,
        streamFactory: factory,
        jitter: false,
      },
    );

    expect(typeof disconnect).toBe('function');
    expect(statuses[0]).toMatchObject({ status: 'connecting' });
    expect(statuses[1]).toMatchObject({ status: 'open' });
    expect(capturedEventHandler).not.toBeNull();

    const emit = (event: AcceleratorArtifactSnapshotEvent | AcceleratorArtifactUpdatesEvent | any) => {
      capturedEventHandler?.(event);
    };

    emit({ type: 'snapshot', revision: 2, artifacts: [{ filename: 'draft.md' }] });
    expect(snapshots).toHaveLength(1);

    emit({ type: 'updates', revision: 2, updates: [{ filename: 'draft.md' }] });
    expect(updates).toHaveLength(0);

    emit({ type: 'updates', revision: 3, updates: [{ filename: 'draft.md', version: 2 }] });
    expect(updates).toHaveLength(1);

    emit({ type: 'updates', revision: 3, updates: [{ filename: 'draft.md', version: 3 }] });
    expect(updates).toHaveLength(1);

    emit({ type: 'heartbeat', revision: 3, heartbeat: true });
    expect(heartbeats).toBe(1);

    disconnect();
  });
});
