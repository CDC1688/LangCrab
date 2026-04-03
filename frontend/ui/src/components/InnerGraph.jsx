import React, { useEffect, useMemo, useCallback, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useStore } from '../store'
import { fetchSessionGraph, fetchSession } from '../api'
import { nodeTypes } from './GraphNode'
import SessionInfoBar from './SessionInfoBar'

export default function InnerGraph() {
  const selectedSid = useStore(s => s.selectedSid)
  const graphData = useStore(s => s.graphData)
  const selectNode = useStore(s => s.selectNode)
  const selectedNode = useStore(s => s.selectedNode)

  // Step-through state (local, not in global store)
  const [stepping, setStepping] = useState(false)
  const [stepIndex, setStepIndex] = useState(0)

  // Load graph data
  useEffect(() => {
    if (!selectedSid) return
    fetchSessionGraph(selectedSid).then(g => {
      useStore.getState().setGraphData(g)
    })
    fetchSession(selectedSid).then(d => {
      useStore.getState().setSessionDetail(d)
    })
    // Reset step-through when session changes
    setStepping(false)
    setStepIndex(0)
  }, [selectedSid])

  // The ordered list of node IDs (execution order)
  const nodeOrder = useMemo(() => {
    if (!graphData?.active_path) return []
    return graphData.active_path
  }, [graphData])

  // Which nodes/edges are visible up to current stepIndex
  const visibleNodes = useMemo(() => {
    if (!stepping) return null // null = show all
    return new Set(nodeOrder.slice(0, stepIndex + 1))
  }, [stepping, stepIndex, nodeOrder])

  const visibleEdges = useMemo(() => {
    if (!stepping || !graphData?.edges) return null
    const visible = new Set()
    const nodeSet = visibleNodes
    for (const e of graphData.edges) {
      if (nodeSet.has(e.source) && nodeSet.has(e.target)) {
        visible.add(e.id)
      }
    }
    return visible
  }, [stepping, visibleNodes, graphData])

  // Build display nodes
  const displayNodes = useMemo(() => {
    if (!graphData?.nodes) return []
    return graphData.nodes.map(n => {
      const isCurrent = stepping && nodeOrder[stepIndex] === n.id
      const isDimmed = stepping && visibleNodes && !visibleNodes.has(n.id)
      return {
        ...n,
        selected: n.id === selectedNode || isCurrent,
        data: {
          ...n.data,
          ...(isDimmed ? { bgColor: '#1e1e2e', borderColor: '#333' } : {}),
        },
      }
    })
  }, [graphData, selectedNode, stepping, stepIndex, visibleNodes, nodeOrder])

  const displayEdges = useMemo(() => {
    if (!graphData?.edges) return []
    if (!stepping) return graphData.edges
    return graphData.edges.map(e => ({
      ...e,
      style: visibleEdges && visibleEdges.has(e.id)
        ? e.style
        : { stroke: '#333', strokeWidth: 1, strokeDasharray: '5,5' },
    }))
  }, [graphData, stepping, visibleEdges])

  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

  useEffect(() => { setNodes(displayNodes) }, [displayNodes, setNodes])
  useEffect(() => { setEdges(displayEdges) }, [displayEdges, setEdges])

  const onNodeClick = useCallback((_, node) => {
    selectNode(node.id)
  }, [selectNode])

  // Step-through controls
  const startStepThrough = useCallback(() => {
    setStepping(true)
    setStepIndex(0)
    if (nodeOrder.length > 0) {
      selectNode(nodeOrder[0])
    }
  }, [nodeOrder, selectNode])

  const stepNext = useCallback(() => {
    const next = Math.min(stepIndex + 1, nodeOrder.length - 1)
    setStepIndex(next)
    selectNode(nodeOrder[next])
  }, [stepIndex, nodeOrder, selectNode])

  const stepPrev = useCallback(() => {
    const prev = Math.max(stepIndex - 1, 0)
    setStepIndex(prev)
    selectNode(nodeOrder[prev])
  }, [stepIndex, nodeOrder, selectNode])

  const exitStepThrough = useCallback(() => {
    setStepping(false)
    setStepIndex(0)
  }, [])

  // Keyboard shortcuts for step-through
  useEffect(() => {
    if (!stepping) return
    const handler = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return
      if (e.key === 'ArrowRight' || e.key === 'j') { e.preventDefault(); stepNext() }
      else if (e.key === 'ArrowLeft' || e.key === 'k') { e.preventDefault(); stepPrev() }
      else if (e.key === 'Escape') { e.preventDefault(); exitStepThrough() }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [stepping, stepNext, stepPrev, exitStepThrough])

  if (!graphData) {
    return <div className="loading">Loading agent trace...</div>
  }

  if (!graphData.nodes || graphData.nodes.length === 0) {
    return (
      <div className="loading">
        <div>
          <p>No agent trace data available for this session.</p>
          <p style={{fontSize: '13px', color: '#888', marginTop: '8px'}}>
            Run extract_traces.py to extract agent behavior from CSV files.
          </p>
        </div>
      </div>
    )
  }

  const sessionDetail = useStore.getState().sessionDetail
  const cls = sessionDetail?.classification || {}
  const traceSteps = graphData.nodes.length
  const turns = graphData.turns?.length || 0

  // Current step info for display
  const currentNodeId = stepping ? nodeOrder[stepIndex] : null
  const currentNodeData = currentNodeId
    ? graphData.nodes.find(n => n.id === currentNodeId)?.data
    : null

  const goBack = () => {
    useStore.getState().goToSessions()
  }

  return (
    <div className="graph-container">
      <SessionInfoBar />
      <div className="graph-title">
        <button className="btn btn-back" onClick={goBack} title="Back to sessions">
          &larr; Back
        </button>
        <h2>Agent Behavior Trace</h2>
        <span className="graph-subtitle">
          {cls.primary_category} / {cls.subcategory} | {cls.model} | {traceSteps} steps, {turns} turns
        </span>
      </div>
      <div className="replay-controls">
        {!stepping && (
          <button className="btn btn-primary" onClick={startStepThrough}>Step Through</button>
        )}
        {stepping && (
          <>
            <button className="btn btn-small" onClick={stepPrev} disabled={stepIndex === 0} title="Previous (← or k)">
              Prev
            </button>
            <button className="btn btn-primary btn-small" onClick={stepNext} disabled={stepIndex >= nodeOrder.length - 1} title="Next (→ or j)">
              Next
            </button>
            <span className="replay-progress">
              Step {stepIndex + 1} / {nodeOrder.length}
            </span>
            {currentNodeData && (
              <span className="step-current-label">
                {currentNodeData.label}
              </span>
            )}
            <button className="btn btn-secondary btn-small" onClick={exitStepThrough} title="Exit (Esc)">
              Exit
            </button>
          </>
        )}
      </div>
      <div className="react-flow-wrapper">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.1}
          maxZoom={2}
          attributionPosition="bottom-left"
        >
          <Background color="#333" gap={20} />
          <Controls />
          <MiniMap
            nodeColor={(node) => {
              const st = node.data?.stepType
              if (st === 'user') return '#1565C0'
              if (st === 'tool_calls') return '#E65100'
              if (st === 'tool_result') return node.data?.isError ? '#C62828' : '#616161'
              if (st === 'assistant') return '#2E7D32'
              if (st === 'converge') return node.data?.errorCount > 0 ? '#C62828' : '#546E7A'
              if (st === 'classification') return '#4527A0'
              return '#666'
            }}
          />
        </ReactFlow>
      </div>
    </div>
  )
}
