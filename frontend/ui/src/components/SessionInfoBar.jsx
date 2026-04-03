import React, { useState } from 'react'
import { useStore } from '../store'

export default function SessionInfoBar() {
  const sessionDetail = useStore(s => s.sessionDetail)
  const [collapsed, setCollapsed] = useState(false)

  if (!sessionDetail) return null

  const cls = sessionDetail.classification || {}
  const t = cls.token_usage || {}
  const errRate = cls.error_rate != null ? (cls.error_rate * 100).toFixed(1) + '%' : '-'
  const totalTokens = t.total_tokens
    ? t.total_tokens >= 1e6 ? (t.total_tokens / 1e6).toFixed(1) + 'M'
    : t.total_tokens >= 1e3 ? (t.total_tokens / 1e3).toFixed(1) + 'K'
    : t.total_tokens
    : '-'

  const errReport = sessionDetail.error_report
  const recoveredCount = errReport
    ? (errReport.tool_errors || []).filter(e => e.recovered).length
    : 0

  const goLogAnalysis = () => {
    const store = useStore.getState()
    store.setView('logAnalysis')
    store.setLogAnalysisSid(cls.sid)
  }

  return (
    <div className="session-info-bar">
      <div className="sib-toggle" onClick={() => setCollapsed(!collapsed)}>
        <span className="sib-title">Session Info</span>
        <span className="sib-arrow">{collapsed ? '▶' : '▼'}</span>
      </div>
      {!collapsed && (
        <div className="sib-content">
          <div className="sib-row">
            <span className="sib-item"><b>{cls.model}</b></span>
            <span className="sib-item">{cls.event_time}</span>
            <span className="sib-item">{cls.num_messages} msgs</span>
            <span className="sib-item">Tokens: {totalTokens}</span>
          </div>
          <div className="sib-row">
            <span className="sib-item">
              <span className="sib-category">{cls.primary_category}</span>
              {' / '}{cls.subcategory}
            </span>
            <span className="sib-item">confidence: <b>{cls.confidence}</b></span>
            <span className="sib-item">heuristic: {cls.heuristic_classified ? 'yes' : 'no'}</span>
          </div>
          <div className="sib-row">
            <span className="sib-item">
              Tools: {cls.tool_success_count + cls.tool_error_count} calls
            </span>
            <span className={`sib-item ${cls.tool_error_count > 0 ? 'sib-error' : ''}`}>
              Errors: {cls.tool_error_count} ({errRate})
              {cls.tool_error_count > 0 && ` · ${recoveredCount} recovered`}
            </span>
            <span className="sib-item">Finish: {cls.finish_reason || '-'}</span>
            <span className="sib-link" onClick={goLogAnalysis}>Log Analysis →</span>
          </div>
        </div>
      )}
    </div>
  )
}
