import React from 'react'
import { Handle, Position } from '@xyflow/react'

// ---- Outer pipeline graph nodes (unchanged) ----

const STATUS_COLORS = {
  success: '#4CAF50',
  error: '#F44336',
  skipped: '#9E9E9E',
  active: '#2196F3',
  inactive: '#BDBDBD',
}

const STATUS_BG = {
  success: '#E8F5E9',
  error: '#FFEBEE',
  skipped: '#F5F5F5',
  active: '#E3F2FD',
  inactive: '#FAFAFA',
}

export function GraphNode({ data, selected }) {
  const { label, status, iterations, preview, retries, sessionCount, isExpandable } = data
  const borderColor = STATUS_COLORS[status] || STATUS_COLORS.inactive
  const bgColor = STATUS_BG[status] || STATUS_BG.inactive

  return (
    <div
      className={`graph-node ${selected ? 'selected' : ''}`}
      style={{ borderColor, backgroundColor: bgColor, borderWidth: selected ? 3 : 2 }}
    >
      <Handle type="target" position={Position.Top} />
      <div className="node-header">
        <span className="node-label">{label}</span>
        {status !== 'skipped' && (
          <span className="node-status-dot" style={{ backgroundColor: borderColor }} />
        )}
      </div>
      {sessionCount != null && <div className="node-badge info">{sessionCount} sessions</div>}
      {preview && <div className="node-preview">{preview}</div>}
      {isExpandable && <div className="node-expand-hint">Click to expand</div>}
      <Handle type="source" position={Position.Bottom} />
    </div>
  )
}

export function StartEndNode({ data }) {
  const isStart = data.label === 'START'
  return (
    <div className={`start-end-node ${isStart ? 'start' : 'end'}`}>
      {!isStart && <Handle type="target" position={Position.Top} />}
      <span>{data.label}</span>
      {isStart && <Handle type="source" position={Position.Bottom} />}
    </div>
  )
}

// ---- Agent behavior nodes (new) ----

const STEP_ICONS = {
  system: '⚙',
  user: '👤',
  tool_calls: '🔧',
  tool_result: '📋',
  assistant: '🤖',
  classification: '🏷',
}

export function AgentNode({ data, selected }) {
  const {
    stepType, label, preview, status, toolNames, toolName,
    isError, borderColor, bgColor, agentText, errorType, recovered,
  } = data

  return (
    <div
      className={`agent-node ${stepType} ${selected ? 'selected' : ''} ${isError ? 'error' : ''}`}
      style={{
        borderColor: borderColor || '#666',
        backgroundColor: bgColor || '#2a2a3e',
        borderWidth: selected ? 3 : 1.5,
      }}
    >
      <Handle type="target" position={Position.Top} />

      <div className="agent-node-header">
        <span className="agent-node-icon">{STEP_ICONS[stepType] || '•'}</span>
        <span className="agent-node-label">{label}</span>
        {isError && !errorType && <span className="agent-node-error-badge">ERR</span>}
        {errorType && (
          <span className="agent-node-error-type">{errorType}</span>
        )}
        {isError && recovered !== undefined && (
          <span className={`agent-node-recovery ${recovered ? 'yes' : 'no'}`}>
            {recovered ? '✓' : '✗'}
          </span>
        )}
      </div>

      {/* Tool calls: show tool name badges */}
      {stepType === 'tool_calls' && toolNames && (
        <div className="agent-node-tools">
          {toolNames.slice(0, 6).map((name, i) => (
            <span key={i} className="tool-badge">{name}</span>
          ))}
          {toolNames.length > 6 && (
            <span className="tool-badge more">+{toolNames.length - 6}</span>
          )}
        </div>
      )}

      {/* Preview text */}
      {preview && (
        <div className={`agent-node-preview ${stepType}`}>
          {preview.slice(0, 100)}{preview.length > 100 ? '...' : ''}
        </div>
      )}

      <Handle type="source" position={Position.Bottom} />
    </div>
  )
}

// Wide variant for user messages and agent responses (outer layer)
export function AgentNodeWide({ data, selected }) {
  const {
    stepType, label, preview,
  } = data

  // Distinct colors per type
  const theme = WIDE_THEMES[stepType] || WIDE_THEMES.system

  return (
    <div
      className={`agent-node-wide ${stepType} ${selected ? 'selected' : ''}`}
      style={{
        borderColor: theme.border,
        backgroundColor: theme.bg,
        borderWidth: selected ? 3 : 2,
      }}
    >
      <Handle type="target" position={Position.Top} />

      <div className="agent-node-wide-header">
        <div className="agent-node-wide-icon-circle" style={{ backgroundColor: theme.iconBg }}>
          <span className="agent-node-wide-icon">{theme.icon}</span>
        </div>
        <span className="agent-node-wide-label" style={{ color: theme.labelColor }}>{label}</span>
      </div>

      {preview && (
        <div className="agent-node-wide-preview" style={{ color: theme.previewColor }}>
          {preview.slice(0, 200)}{preview.length > 200 ? '...' : ''}
        </div>
      )}

      <Handle type="source" position={Position.Bottom} />
    </div>
  )
}

const WIDE_THEMES = {
  user: {
    border: '#1976D2',
    bg: '#0D2744',
    iconBg: '#1565C0',
    icon: '👤',
    labelColor: '#64B5F6',
    previewColor: '#90CAF9',
  },
  assistant: {
    border: '#2E7D32',
    bg: '#0D2E10',
    iconBg: '#2E7D32',
    icon: '🤖',
    labelColor: '#81C784',
    previewColor: '#A5D6A7',
  },
  system: {
    border: '#6A1B9A',
    bg: '#1A0A2E',
    iconBg: '#7B1FA2',
    icon: '⚙',
    labelColor: '#CE93D8',
    previewColor: '#CE93D8',
  },
}

// Converge node — synthetic join point after parallel tool results
export function ConvergeNode({ data, selected }) {
  const { label, borderColor, bgColor, errorCount, resultCount, status } = data
  const hasError = errorCount > 0

  return (
    <div
      className={`converge-node ${selected ? 'selected' : ''} ${hasError ? 'has-error' : ''}`}
      style={{
        borderColor: borderColor || '#546E7A',
        backgroundColor: bgColor || '#263238',
        borderWidth: selected ? 3 : 1.5,
      }}
    >
      <Handle type="target" position={Position.Top} />
      <div className="converge-node-inner">
        <span className="converge-icon">{hasError ? '⚠' : '◆'}</span>
        <span className="converge-label">{label}</span>
        {resultCount != null && (
          <span className="converge-count">{resultCount} results</span>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  )
}

export const nodeTypes = {
  graphNode: GraphNode,
  startEnd: StartEndNode,
  agentNode: AgentNode,
  agentNodeWide: AgentNodeWide,
  convergeNode: ConvergeNode,
}
