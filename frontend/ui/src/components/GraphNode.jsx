import React, { useState } from 'react'
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
  thinking: '💭',
  converge: '◆',
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

// ---- Group node (collapsible container for agent actions) ----

const GROUP_THEMES = {
  tool_fan: { accent: '#E65100', headerBg: 'rgba(230, 81, 0, 0.15)', icon: '🔧' },
  retry_loop: { accent: '#C62828', headerBg: 'rgba(198, 40, 40, 0.15)', icon: '🔄' },
  sub_agent: { accent: '#6A1B9A', headerBg: 'rgba(106, 27, 154, 0.15)', icon: '🤖' },
}

export function GroupNode({ data, selected }) {
  const {
    label, groupType, width, height, childCount,
  } = data
  const theme = GROUP_THEMES[groupType] || GROUP_THEMES.tool_fan

  return (
    <div
      className={`group-node ${groupType} ${selected ? 'selected' : ''}`}
      style={{
        borderColor: theme.accent,
        backgroundColor: 'rgba(30, 30, 46, 0.4)',
        width: width || 400,
        height: height || 200,
        borderWidth: selected ? 2.5 : 1.5,
        borderStyle: 'dashed',
        borderRadius: 12,
        position: 'relative',
      }}
    >
      <Handle type="target" position={Position.Top} />
      <div
        className="group-node-header"
        style={{
          backgroundColor: theme.headerBg,
          borderBottom: `1px solid ${theme.accent}40`,
        }}
      >
        <span className="group-node-icon">{theme.icon}</span>
        <span className="group-node-label" style={{ color: theme.accent }}>{label}</span>
        <span className="group-node-badge">{childCount} steps</span>
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  )
}

// ---- Thinking node (agent reasoning before tool calls) ----

export function ThinkingNode({ data, selected }) {
  const [expanded, setExpanded] = useState(false)
  const { label, preview, fullContent, borderColor, bgColor } = data

  return (
    <div
      className={`thinking-node ${selected ? 'selected' : ''}`}
      style={{
        borderColor: borderColor || '#78909C',
        backgroundColor: bgColor || '#1a1a2e',
        borderWidth: selected ? 3 : 1.5,
        borderStyle: 'dashed',
      }}
      onClick={(e) => { e.stopPropagation(); setExpanded(!expanded) }}
    >
      <Handle type="target" position={Position.Top} />
      <div className="thinking-node-header">
        <span className="thinking-node-icon">{STEP_ICONS.thinking}</span>
        <span className="thinking-node-label">{label || 'Agent Reasoning'}</span>
        <span className="thinking-node-toggle">{expanded ? '▲' : '▼'}</span>
      </div>
      <div className={`thinking-node-content ${expanded ? 'expanded' : ''}`}>
        {expanded
          ? (fullContent || preview || '').slice(0, 800)
          : (preview || '').slice(0, 120)
        }
        {!expanded && (fullContent || '').length > 120 && '...'}
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  )
}

// ---- Retry node (agent decision that retries after an error) ----

export function RetryNode({ data, selected }) {
  const {
    label, preview, toolNames, retryAttempt,
    borderColor, bgColor,
  } = data

  return (
    <div
      className={`retry-node ${selected ? 'selected' : ''}`}
      style={{
        borderColor: borderColor || '#C62828',
        backgroundColor: bgColor || '#2a1a1a',
        borderWidth: selected ? 3 : 1.5,
        borderLeftWidth: 4,
        borderLeftColor: '#C62828',
      }}
    >
      <Handle type="target" position={Position.Top} />
      <div className="retry-node-header">
        <span className="retry-node-icon">🔄</span>
        <span className="retry-node-label">{label}</span>
        {retryAttempt && (
          <span className="retry-node-attempt">Attempt {retryAttempt}</span>
        )}
      </div>
      {toolNames && (
        <div className="agent-node-tools">
          {toolNames.slice(0, 4).map((name, i) => (
            <span key={i} className="tool-badge retry">{name}</span>
          ))}
        </div>
      )}
      {preview && (
        <div className="agent-node-preview tool_calls">
          {preview.slice(0, 80)}{preview.length > 80 ? '...' : ''}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} />
    </div>
  )
}

// ---- Sub-agent node (group variant for sub-agent invocations) ----

export function SubAgentNode({ data, selected }) {
  const { label, width, height, childCount } = data

  return (
    <div
      className={`sub-agent-node ${selected ? 'selected' : ''}`}
      style={{
        borderColor: '#6A1B9A',
        backgroundColor: 'rgba(26, 10, 46, 0.5)',
        width: width || 400,
        height: height || 200,
        borderWidth: selected ? 2.5 : 2,
        borderStyle: 'solid',
        borderRadius: 12,
        position: 'relative',
      }}
    >
      <Handle type="target" position={Position.Top} />
      <div className="sub-agent-node-header">
        <span className="sub-agent-node-icon">🤖</span>
        <span className="sub-agent-node-label">{label || 'Sub-Agent'}</span>
        {childCount && (
          <span className="sub-agent-node-badge">{childCount} steps</span>
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
  groupNode: GroupNode,
  thinkingNode: ThinkingNode,
  retryNode: RetryNode,
  subAgentNode: SubAgentNode,
}
