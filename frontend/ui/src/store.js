import { create } from 'zustand'

export const useStore = create((set, get) => ({
  // View state
  view: 'sessions', // 'sessions' | 'session' | 'dashboard'
  selectedSid: null,
  selectedNode: null,
  breadcrumb: [],

  // Data
  sessions: [],
  sessionsTotal: 0,
  filters: null,
  summary: null,
  sessionDetail: null,
  graphData: null,
  pipelineGraph: null,
  annotations: [],
  annotationProgress: null,

  // Filter state
  activeFilters: {
    category: null,
    subcategory: null,
    model: null,
    confidence: null,
    has_errors: null,
    keyword: '',
    annotation_status: null,
  },
  offset: 0,
  limit: 50,

  // Cross-link support
  logAnalysisSid: null,

  // WebSocket replay
  replayState: null, // null | 'playing' | 'paused' | 'complete'
  replaySpeed: 1.0,
  activeNodes: new Set(),
  activeEdges: new Set(),

  // Actions
  setView: (view) => set({ view }),

  selectSession: (sid) => set({
    selectedSid: sid,
    selectedNode: null,
    view: 'session',
    breadcrumb: ['Pipeline', 'classify_row', sid.slice(0, 16) + '...'],
  }),

  selectNode: (nodeId) => set({ selectedNode: nodeId }),

  goToPipeline: () => set({
    view: 'sessions',
    selectedSid: null,
    selectedNode: null,
    breadcrumb: [],
    graphData: null,
    sessionDetail: null,
  }),

  goToSessions: () => set({
    view: 'sessions',
    selectedSid: null,
    selectedNode: null,
    breadcrumb: ['Pipeline', 'classify_row'],
  }),

  setFilter: (key, value) => set((state) => ({
    activeFilters: { ...state.activeFilters, [key]: value || null },
    offset: 0,
  })),

  setLogAnalysisSid: (sid) => set({ logAnalysisSid: sid }),

  clearFilters: () => set({
    activeFilters: {
      category: null,
      subcategory: null,
      model: null,
      confidence: null,
      has_errors: null,
      keyword: '',
      annotation_status: null,
    },
    offset: 0,
  }),

  setOffset: (offset) => set({ offset }),

  setSessions: (sessions, total) => set({ sessions, sessionsTotal: total }),
  setFilters: (filters) => set({ filters }),
  setSummary: (summary) => set({ summary }),
  setSessionDetail: (detail) => set({ sessionDetail: detail }),
  setGraphData: (data) => set({ graphData: data }),
  setPipelineGraph: (data) => set({ pipelineGraph: data }),
  setAnnotations: (annotations, progress) => set({ annotations, annotationProgress: progress }),

  // Replay actions
  setReplayState: (replayState) => set({ replayState }),
  setReplaySpeed: (speed) => set({ replaySpeed: speed }),
  setActiveNodes: (nodes) => set({ activeNodes: new Set(nodes) }),
  addActiveNode: (node) => set((s) => {
    const next = new Set(s.activeNodes)
    next.add(node)
    return { activeNodes: next }
  }),
  addActiveEdge: (edge) => set((s) => {
    const next = new Set(s.activeEdges)
    next.add(edge)
    return { activeEdges: next }
  }),
  resetReplay: () => set({
    replayState: null,
    activeNodes: new Set(),
    activeEdges: new Set(),
    selectedNode: null,
  }),
}))
