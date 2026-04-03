import React, { useMemo, useState } from 'react'
import { JsonView, darkStyles } from 'react-json-view-lite'
import 'react-json-view-lite/dist/index.css'
import { useStore } from '../store'

export default function StatePanel() {
  const selectedNode = useStore(s => s.selectedNode)
  const graphData = useStore(s => s.graphData)
  const [activeTab, setActiveTab] = useState('input')

  const nodeState = useMemo(() => {
    if (!graphData?.node_states || !selectedNode) return null
    return graphData.node_states[selectedNode] || null
  }, [graphData, selectedNode])

  const diff = useMemo(() => {
    if (!nodeState?.input || !nodeState?.output) return null
    return computeDiff(nodeState.input, nodeState.output)
  }, [nodeState])

  if (!selectedNode || !nodeState) {
    return (
      <div className="state-panel">
        <div className="state-panel-header">
          <h3>State Inspector</h3>
        </div>
        <div className="state-panel-empty">
          Click a node to inspect its state
        </div>
      </div>
    )
  }

  const nodeLabel = selectedNode.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

  return (
    <div className="state-panel">
      <div className="state-panel-header">
        <h3>{nodeLabel}</h3>
        <button className="close-btn" onClick={() => useStore.getState().selectNode(null)}>
          &times;
        </button>
      </div>

      <div className="state-tabs">
        <button className={activeTab === 'input' ? 'active' : ''} onClick={() => setActiveTab('input')}>
          Input
        </button>
        <button className={activeTab === 'output' ? 'active' : ''} onClick={() => setActiveTab('output')}>
          Output
        </button>
        <button className={activeTab === 'diff' ? 'active' : ''} onClick={() => setActiveTab('diff')}>
          Diff
        </button>
      </div>

      <div className="state-content">
        {activeTab === 'input' && nodeState.input && (
          <JsonView data={nodeState.input} style={darkStyles} shouldExpandNode={expandFirstLevel} />
        )}
        {activeTab === 'output' && nodeState.output && (
          <>
            {/* Rich error card if error_detail exists */}
            {nodeState.output.error_detail && (
              <ErrorDetailCard detail={nodeState.output.error_detail} />
            )}
            <JsonView data={nodeState.output} style={darkStyles} shouldExpandNode={expandFirstLevel} />
          </>
        )}
        {activeTab === 'diff' && diff && (
          <DiffView diff={diff} />
        )}
        {activeTab === 'diff' && !diff && (
          <div className="state-panel-empty">No diff available</div>
        )}
      </div>
    </div>
  )
}

function expandFirstLevel(level) {
  return level < 2
}

function DiffView({ diff }) {
  return (
    <div className="diff-view">
      {diff.map((item, i) => (
        <div key={i} className={`diff-item diff-${item.type}`}>
          <span className="diff-icon">
            {item.type === 'added' ? '+' : item.type === 'changed' ? '~' : '-'}
          </span>
          <span className="diff-key">{item.key}:</span>
          {item.type === 'changed' ? (
            <span className="diff-value">
              <span className="diff-old">{JSON.stringify(item.oldValue)}</span>
              <span className="diff-arrow"> → </span>
              <span className="diff-new">{JSON.stringify(item.newValue)}</span>
            </span>
          ) : (
            <span className="diff-value">{JSON.stringify(item.value)}</span>
          )}
        </div>
      ))}
      {diff.length === 0 && <div className="state-panel-empty">No changes</div>}
    </div>
  )
}

function ErrorDetailCard({ detail }) {
  return (
    <div className="error-detail-card">
      <div className="edc-header">
        <span className="edc-type">{detail.error_type}</span>
        <span className={`edc-recovery ${detail.recovered ? 'yes' : 'no'}`}>
          {detail.recovered ? '✓ Recovered' : '✗ Not recovered'}
        </span>
      </div>
      <div className="edc-label">Error Message</div>
      <pre className="edc-pre">{detail.error_text}</pre>
      {detail.current_summary && (
        <>
          <div className="edc-label">What agent was doing</div>
          <div className="edc-context">{detail.current_summary}</div>
        </>
      )}
      {detail.previous_summary && (
        <>
          <div className="edc-label">Previous context</div>
          <div className="edc-context">{detail.previous_summary}</div>
        </>
      )}
      {detail.recovered && detail.recovery_message && (
        <>
          <div className="edc-label">Recovery</div>
          <div className="edc-context success">{detail.recovery_message}</div>
        </>
      )}
      <div className="edc-meta">Message position: #{detail.position}</div>
    </div>
  )
}

function computeDiff(input, output) {
  const diff = []
  const allKeys = new Set([...Object.keys(input), ...Object.keys(output)])

  for (const key of allKeys) {
    const inVal = input[key]
    const outVal = output[key]

    if (inVal === undefined && outVal !== undefined) {
      diff.push({ type: 'added', key, value: outVal })
    } else if (inVal !== undefined && outVal === undefined) {
      diff.push({ type: 'removed', key, value: inVal })
    } else if (JSON.stringify(inVal) !== JSON.stringify(outVal)) {
      diff.push({ type: 'changed', key, oldValue: inVal, newValue: outVal })
    }
  }

  return diff
}
