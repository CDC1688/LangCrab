import React from 'react'
import { useStore } from '../store'

const STATUS_COLORS = {
  approved: '#4CAF50',
  rejected: '#F44336',
  flagged: '#FF9800',
  corrected: '#2196F3',
}

export default function SessionList() {
  const sessions = useStore(s => s.sessions)
  const sessionsTotal = useStore(s => s.sessionsTotal)
  const selectSession = useStore(s => s.selectSession)
  const offset = useStore(s => s.offset)
  const limit = useStore(s => s.limit)
  const setOffset = useStore(s => s.setOffset)

  const totalPages = Math.ceil(sessionsTotal / limit)
  const currentPage = Math.floor(offset / limit) + 1

  return (
    <div className="session-list">
      <div className="session-list-header">
        <h2>Sessions</h2>
        <span className="session-count">{sessionsTotal} total</span>
      </div>

      <div className="session-table-wrapper">
        <table className="session-table">
          <thead>
            <tr>
              <th>SID</th>
              <th>Category</th>
              <th>Subcategory</th>
              <th>Model</th>
              <th>Confidence</th>
              <th>Iter</th>
              <th>Errors</th>
              <th>Messages</th>
              <th>Status</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map(s => (
              <tr key={s.sid} onClick={() => selectSession(s.sid)} className="session-row">
                <td className="sid-cell" title={s.sid}>{s.sid.slice(0, 12)}...</td>
                <td>
                  <span className="category-tag">{s.primary_category}</span>
                </td>
                <td>{s.subcategory}</td>
                <td className="model-cell">{s.model}</td>
                <td>
                  <span className={`confidence-badge ${s.confidence}`}>{s.confidence}</span>
                </td>
                <td className={s.iterations > 1 ? 'retry-cell' : ''}>
                  {s.heuristic_classified ? 'H' : s.iterations}
                </td>
                <td className={s.tool_error_count > 0 ? 'error-cell' : ''}>
                  {s.tool_error_count}
                </td>
                <td>{s.num_messages}</td>
                <td>
                  {s.annotation_status && (
                    <span
                      className="annotation-dot"
                      style={{ backgroundColor: STATUS_COLORS[s.annotation_status] || '#9E9E9E' }}
                      title={s.annotation_status}
                    />
                  )}
                </td>
                <td className="time-cell">{s.event_time}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="pagination">
          <button disabled={currentPage === 1} onClick={() => setOffset(offset - limit)}>Prev</button>
          <span>Page {currentPage} of {totalPages}</span>
          <button disabled={currentPage >= totalPages} onClick={() => setOffset(offset + limit)}>Next</button>
        </div>
      )}
    </div>
  )
}
