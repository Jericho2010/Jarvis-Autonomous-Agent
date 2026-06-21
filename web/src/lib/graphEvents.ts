export type GraphEventKind = 'handoff' | 'tool_start' | 'tool_done' | 'agent';

export interface GraphEvent {
  ts: number;
  kind: GraphEventKind;
  agent?: string;
  tool?: string;
  detail?: string;
}

export const MAX_GRAPH_EVENTS = 20;
export const MAX_LOG_LINES = 300;

export function formatGraphEventLabel(event: GraphEvent): string {
  switch (event.kind) {
    case 'handoff':
      return event.detail
        ? `Handoff: ${event.detail}`
        : `Handoff → ${(event.agent || 'unknown').toUpperCase()}`;
    case 'tool_start':
      return `${(event.agent || 'agent').toUpperCase()}: ${event.tool || 'tool'} started`;
    case 'tool_done':
      return `${(event.agent || 'agent').toUpperCase()}: ${event.tool || 'tool'} done`;
    case 'agent':
      return `Active agent: ${(event.agent || 'jarvis').toUpperCase()}`;
    default:
      return event.detail || 'Event';
  }
}
