import React, { useCallback, useMemo } from 'react'
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
import { nodeTypes } from './GraphNode'

export default function OuterGraph() {
  const pipelineGraph = useStore(s => s.pipelineGraph)
  const goToSessions = useStore(s => s.goToSessions)
  const summary = useStore(s => s.summary)

  const initialNodes = useMemo(() => pipelineGraph?.nodes || [], [pipelineGraph])
  const initialEdges = useMemo(() => pipelineGraph?.edges || [], [pipelineGraph])

  const [nodes, , onNodesChange] = useNodesState(initialNodes)
  const [edges, , onEdgesChange] = useEdgesState(initialEdges)

  const onNodeClick = useCallback((_, node) => {
    if (node.data.isExpandable || node.id === 'classify_row') {
      goToSessions()
    }
  }, [goToSessions])

  if (!pipelineGraph) {
    return <div className="loading">Loading pipeline graph...</div>
  }

  return (
    <div className="graph-container">
      <div className="graph-title">
        <h2>Pipeline Graph</h2>
        {summary && (
          <span className="graph-subtitle">
            {summary.total} sessions | {summary.heuristic_count} heuristic | {summary.llm_count} LLM | {summary.retry_count} retries
          </span>
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
          minZoom={0.5}
          maxZoom={2}
          attributionPosition="bottom-left"
        >
          <Background color="#f0f0f0" gap={20} />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </div>
    </div>
  )
}
