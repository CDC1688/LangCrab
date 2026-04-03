import React from 'react'
import { useStore } from '../store'

export default function Timeline() {
  const graphData = useStore(s => s.graphData)

  if (!graphData?.active_path) return null

  const nodes = graphData.nodes.filter(n => graphData.active_path.includes(n.id))
  const nodeStates = graphData.node_states || {}

  return (
    <div className="timeline">
      <h4>Execution Timeline</h4>
      <div className="timeline-steps">
        {nodes.map((node, i) => {
          const state = nodeStates[node.id]
          const isLast = i === nodes.length - 1
          return (
            <div key={node.id} className={`timeline-step ${node.data.status}`}>
              <div className="timeline-dot" />
              {!isLast && <div className="timeline-line" />}
              <div className="timeline-content">
                <span className="timeline-label">{node.data.label}</span>
                {node.data.iterations > 0 && (
                  <span className="timeline-badge">iter: {node.data.iterations}</span>
                )}
                {node.data.preview && (
                  <span className="timeline-preview">{node.data.preview}</span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
