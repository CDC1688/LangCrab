import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { fetchSubcategoryCounts } from '../api'

const CAT_CN = {
  coding: '编程开发', communication: '通讯交流', content_creation: '内容创作',
  data_analysis: '数据分析', file_management: '文件管理', finance_crypto: '金融加密',
  memory_management: '记忆管理', other: '其他', system_maintenance: '系统维护',
  web_research: '网络搜索', scheduling: '任务调度', agent_orchestration: '代理编排',
}

export default function Dashboard() {
  const summary = useStore(s => s.summary)
  const setFilter = useStore(s => s.setFilter)
  const setView = useStore(s => s.setView)
  const goToSessions = useStore(s => s.goToSessions)

  const [drillCategory, setDrillCategory] = useState(null)
  const [subcategoryCounts, setSubcategoryCounts] = useState(null)

  useEffect(() => {
    if (!drillCategory) {
      setSubcategoryCounts(null)
      return
    }
    fetchSubcategoryCounts(drillCategory).then(d => {
      setSubcategoryCounts(d.counts || {})
    })
  }, [drillCategory])

  if (!summary) {
    return <div className="loading">Loading dashboard...</div>
  }

  const categoryData = Object.entries(summary.category_counts || {}).sort((a, b) => b[1] - a[1])
  const total = summary.total || 1
  const errorStats = summary.error_stats || {}
  const tokenUsage = summary.token_usage || {}
  const confidenceCounts = summary.confidence_counts || {}
  const languageCounts = summary.language_counts || {}

  const handleCategoryClick = (category) => {
    setFilter('category', category)
    goToSessions()
  }

  const handlePieCategoryClick = (category) => {
    setDrillCategory(prev => prev === category ? null : category)
  }

  // Build pie data for categories
  const categoryPieData = {}
  categoryData.forEach(([cat, count]) => { categoryPieData[cat] = count })

  return (
    <div className="dashboard">
      <h2>Dashboard</h2>

      <div className="stats-grid">
        <StatCard label="Total Sessions" value={summary.total} />
        <StatCard label="Heuristic" value={summary.heuristic_count} color="#9C27B0" />
        <StatCard label="LLM Classified" value={summary.llm_count} color="#2196F3" />
        <StatCard label="Needed Retries" value={summary.retry_count} color="#FF9800" />
        <StatCard label="Sessions w/ Errors" value={errorStats.sessions_with_errors} color="#F44336" />
        <StatCard label="Recovered" value={errorStats.sessions_recovered} color="#4CAF50" />
        <StatCard label="Error Loops (3+)" value={errorStats.error_loops} color="#F44336" />
        <StatCard label="Total Tokens" value={formatNumber(tokenUsage.total_prompt_tokens + tokenUsage.total_completion_tokens)} color="#607D8B" />
      </div>

      <div className="chart-grid">
        <div className="chart-card chart-card-wide">
          <h3>主分类分布 (Primary Category Distribution)</h3>
          <div className="pie-drill-container">
            <div className="pie-section">
              <PieChart
                data={categoryPieData}
                colors={CATEGORY_COLORS}
                labels={CAT_CN}
                onSliceClick={handlePieCategoryClick}
                activeSlice={drillCategory}
                title="主分类"
              />
            </div>
            {drillCategory && subcategoryCounts && (
              <div className="pie-section">
                <div className="subcategory-header">
                  <h4>{CAT_CN[drillCategory] || drillCategory} - 子分类分布</h4>
                  <button className="btn btn-small" onClick={() => setDrillCategory(null)}>Back</button>
                </div>
                <PieChart
                  data={subcategoryCounts}
                  colors={{}}
                  labels={{}}
                  title="子分类"
                />
              </div>
            )}
          </div>
        </div>

        <div className="chart-card">
          <h3>Category Distribution</h3>
          <div className="bar-chart">
            {categoryData.map(([cat, count]) => (
              <div key={cat} className="bar-row" onClick={() => handleCategoryClick(cat)}>
                <span className="bar-label">{cat}</span>
                <div className="bar-track">
                  <div
                    className="bar-fill"
                    style={{
                      width: `${(count / total) * 100}%`,
                      backgroundColor: CATEGORY_COLORS[cat] || '#9E9E9E',
                    }}
                  />
                </div>
                <span className="bar-value">{count} ({((count / total) * 100).toFixed(1)}%)</span>
              </div>
            ))}
          </div>
        </div>

        {errorStats.error_type_counts && Object.keys(errorStats.error_type_counts).length > 0 && (
          <div className="chart-card">
            <h3 style={{ cursor: 'pointer' }} onClick={() => setView('errorReport')}>Error Types</h3>
            <div className="bar-chart">
              {Object.entries(errorStats.error_type_counts)
                .sort((a, b) => b[1] - a[1])
                .map(([type, count]) => (
                  <div key={type} className="bar-row" onClick={() => setView('errorReport')}>
                    <span className="bar-label">{type}</span>
                    <div className="bar-track">
                      <div className="bar-fill error" style={{ width: `${(count / Math.max(...Object.values(errorStats.error_type_counts))) * 100}%` }} />
                    </div>
                    <span className="bar-value">{count}</span>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function StatCard({ label, value, color }) {
  return (
    <div className="stat-card">
      <div className="stat-value" style={color ? { color } : {}}>{value ?? 0}</div>
      <div className="stat-label">{label}</div>
    </div>
  )
}

// Auto-color generator for subcategories
const AUTO_COLORS = [
  '#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A',
  '#19D3F3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52',
  '#72B7B2', '#BAB0AC', '#E45756', '#54A24B', '#4C78A8',
  '#F58518', '#EECA3B', '#B279A2', '#9D755D', '#FF9DA6',
]

function PieChart({ data, colors, labels, onSliceClick, activeSlice, title }) {
  const entries = Object.entries(data).filter(([_, v]) => v > 0).sort((a, b) => b[1] - a[1])
  const total = entries.reduce((s, [_, v]) => s + v, 0)
  if (total === 0) return <div className="state-panel-empty">No data</div>

  let cumulative = 0
  const segments = entries.map(([key, value], i) => {
    const start = cumulative / total
    cumulative += value
    const end = cumulative / total
    const color = colors[key] || AUTO_COLORS[i % AUTO_COLORS.length]
    return { key, value, start, end, color }
  })

  const [hoveredIdx, setHoveredIdx] = useState(null)

  const size = 200
  const cx = size / 2
  const cy = size / 2
  const r = 80
  const legendStart = size - 10

  return (
    <svg viewBox={`0 0 ${size} ${legendStart + segments.length * 18 + 10}`} className="pie-svg">
      {segments.map((seg, i) => {
        const startAngle = seg.start * 2 * Math.PI - Math.PI / 2
        const endAngle = seg.end * 2 * Math.PI - Math.PI / 2
        const largeArc = seg.end - seg.start > 0.5 ? 1 : 0
        const x1 = cx + r * Math.cos(startAngle)
        const y1 = cy + r * Math.sin(startAngle)
        const x2 = cx + r * Math.cos(endAngle)
        const y2 = cy + r * Math.sin(endAngle)
        const isActive = activeSlice === seg.key
        const isHovered = hoveredIdx === i
        const scale = isActive || isHovered ? 1.06 : 1
        const path = `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} Z`
        return (
          <path
            key={seg.key}
            d={path}
            fill={seg.color}
            stroke={isActive ? '#fff' : '#1e1e2e'}
            strokeWidth={isActive ? 3 : 1.5}
            style={{
              cursor: onSliceClick ? 'pointer' : 'default',
              transform: `scale(${scale})`,
              transformOrigin: `${cx}px ${cy}px`,
              transition: 'transform 0.2s',
              opacity: activeSlice && !isActive ? 0.4 : 1,
            }}
            onClick={() => onSliceClick && onSliceClick(seg.key)}
            onMouseEnter={() => setHoveredIdx(i)}
            onMouseLeave={() => setHoveredIdx(null)}
          />
        )
      })}
      <text x={cx} y={cy} textAnchor="middle" dy="0.3em" fill="#fff" fontSize="14" fontWeight="bold">{title}</text>
      {/* Legend */}
      {segments.map((seg, i) => {
        const label = labels[seg.key] || seg.key
        const pct = ((seg.value / total) * 100).toFixed(1)
        return (
          <g
            key={seg.key}
            transform={`translate(0, ${legendStart + i * 18})`}
            style={{ cursor: onSliceClick ? 'pointer' : 'default' }}
            onClick={() => onSliceClick && onSliceClick(seg.key)}
            onMouseEnter={() => setHoveredIdx(i)}
            onMouseLeave={() => setHoveredIdx(null)}
          >
            <rect x="10" y="-6" width="10" height="10" fill={seg.color} rx="2" />
            <text x="24" y="3" fill={activeSlice === seg.key ? '#fff' : '#ccc'} fontSize="11">
              {label}: {seg.value} ({pct}%)
            </text>
          </g>
        )
      })}
    </svg>
  )
}

function DonutChart({ data, colors }) {
  const entries = Object.entries(data).filter(([_, v]) => v > 0)
  const total = entries.reduce((s, [_, v]) => s + v, 0)
  if (total === 0) return <div className="state-panel-empty">No data</div>

  let cumulative = 0
  const segments = entries.map(([key, value]) => {
    const start = cumulative / total
    cumulative += value
    const end = cumulative / total
    return { key, value, start, end, color: colors[key] || '#9E9E9E' }
  })

  return (
    <svg viewBox="0 0 200 200" className="donut-svg">
      {segments.map(seg => {
        const startAngle = seg.start * 2 * Math.PI - Math.PI / 2
        const endAngle = seg.end * 2 * Math.PI - Math.PI / 2
        const largeArc = seg.end - seg.start > 0.5 ? 1 : 0
        const x1 = 100 + 80 * Math.cos(startAngle)
        const y1 = 100 + 80 * Math.sin(startAngle)
        const x2 = 100 + 80 * Math.cos(endAngle)
        const y2 = 100 + 80 * Math.sin(endAngle)
        const path = `M 100 100 L ${x1} ${y1} A 80 80 0 ${largeArc} 1 ${x2} ${y2} Z`
        return <path key={seg.key} d={path} fill={seg.color} stroke="#fff" strokeWidth="2" />
      })}
      <circle cx="100" cy="100" r="45" fill="#1e1e2e" />
      <text x="100" y="100" textAnchor="middle" dy="0.3em" fill="#fff" fontSize="20" fontWeight="bold">{total}</text>
      {/* Legend */}
      {segments.map((seg, i) => (
        <g key={seg.key} transform={`translate(0, ${155 + i * 16})`}>
          <rect x="10" y="-6" width="10" height="10" fill={seg.color} rx="2" />
          <text x="24" y="3" fill="#ccc" fontSize="11">{seg.key}: {seg.value}</text>
        </g>
      ))}
    </svg>
  )
}

function formatNumber(n) {
  if (n == null) return '0'
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K'
  return String(n)
}

const CATEGORY_COLORS = {
  coding: '#636EFA',
  file_management: '#EF553B',
  web_research: '#00CC96',
  scheduling: '#AB63FA',
  communication: '#FFA15A',
  data_analysis: '#19D3F3',
  system_maintenance: '#FF6692',
  content_creation: '#B6E880',
  finance_crypto: '#FF97FF',
  memory_management: '#FECB52',
  agent_orchestration: '#72B7B2',
  other: '#BAB0AC',
}
