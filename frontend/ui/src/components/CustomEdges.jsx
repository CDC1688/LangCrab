import React from 'react'
import { BaseEdge, getSmoothStepPath, getBezierPath } from '@xyflow/react'

/**
 * RetryEdge — red dashed curved edge for retry back-edges.
 * Routes to the left of source/target to avoid crossing the main spine.
 */
export function RetryEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  label,
  labelStyle,
  style = {},
  markerEnd,
}) {
  // Route the retry edge to the left to make the loop visible
  const offsetX = -120
  const midX = Math.min(sourceX, targetX) + offsetX
  const midY = (sourceY + targetY) / 2

  const path = `M ${sourceX} ${sourceY}
    C ${midX} ${sourceY}, ${midX} ${targetY}, ${targetX} ${targetY}`

  return (
    <>
      <path
        id={id}
        className="react-flow__edge-path retry-edge-path"
        d={path}
        style={{
          stroke: '#C62828',
          strokeWidth: 2,
          strokeDasharray: '8,4',
          fill: 'none',
          ...style,
        }}
        markerEnd={markerEnd}
      />
      {/* Animated dash */}
      <path
        className="retry-edge-animated"
        d={path}
        style={{
          stroke: '#EF5350',
          strokeWidth: 2,
          strokeDasharray: '4,12',
          strokeDashoffset: 0,
          fill: 'none',
          animation: 'retryDash 1.5s linear infinite',
        }}
      />
      {label && (
        <text>
          <textPath
            href={`#${id}`}
            startOffset="50%"
            textAnchor="middle"
            style={{
              fontSize: 10,
              fontWeight: 'bold',
              fill: '#C62828',
              ...labelStyle,
            }}
          >
            {label}
          </textPath>
        </text>
      )}
    </>
  )
}

/**
 * DataFlowEdge — smooth step edge with a small tool name label.
 * Used for fan-out/fan-in edges to show what data flows.
 */
export function DataFlowEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  label,
  labelStyle,
  style = {},
  markerEnd,
}) {
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 8,
  })

  return (
    <>
      <BaseEdge id={id} path={edgePath} style={style} markerEnd={markerEnd} />
      {label && (
        <foreignObject
          x={labelX - 40}
          y={labelY - 10}
          width={80}
          height={20}
          className="data-flow-label-container"
        >
          <div
            className="data-flow-label"
            style={{
              fontSize: 9,
              color: '#E65100',
              textAlign: 'center',
              background: 'rgba(30, 30, 46, 0.85)',
              borderRadius: 3,
              padding: '1px 4px',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              ...labelStyle,
            }}
          >
            {label}
          </div>
        </foreignObject>
      )}
    </>
  )
}

export const edgeTypes = {
  retryEdge: RetryEdge,
  dataFlowEdge: DataFlowEdge,
}
