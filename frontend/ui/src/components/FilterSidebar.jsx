import React from 'react'
import { useStore } from '../store'

export default function FilterSidebar() {
  const filters = useStore(s => s.filters)
  const activeFilters = useStore(s => s.activeFilters)
  const setFilter = useStore(s => s.setFilter)
  const clearFilters = useStore(s => s.clearFilters)
  const annotationProgress = useStore(s => s.annotationProgress)

  if (!filters) return null

  return (
    <div className="filter-sidebar">
      <div className="filter-header">
        <h3>Filters</h3>
        <button className="btn btn-small" onClick={clearFilters}>Clear</button>
      </div>

      <div className="filter-group">
        <label>Category</label>
        <select
          value={activeFilters.category || ''}
          onChange={e => setFilter('category', e.target.value)}
        >
          <option value="">All</option>
          {filters.categories.map(c => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>

      <div className="filter-group">
        <label>Subcategory</label>
        <select
          value={activeFilters.subcategory || ''}
          onChange={e => setFilter('subcategory', e.target.value)}
        >
          <option value="">All</option>
          {(filters.subcategories || []).map(c => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>

      <div className="filter-group">
        <label>Model</label>
        <select
          value={activeFilters.model || ''}
          onChange={e => setFilter('model', e.target.value)}
        >
          <option value="">All</option>
          {filters.models.map(m => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </div>

      <div className="filter-group">
        <label>Confidence</label>
        <select
          value={activeFilters.confidence || ''}
          onChange={e => setFilter('confidence', e.target.value)}
        >
          <option value="">All</option>
          {filters.confidences.map(c => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>

      <div className="filter-group">
        <label>Has Errors</label>
        <select
          value={activeFilters.has_errors === null ? '' : String(activeFilters.has_errors)}
          onChange={e => {
            const v = e.target.value
            setFilter('has_errors', v === '' ? null : v === 'true')
          }}
        >
          <option value="">All</option>
          <option value="true">With errors</option>
          <option value="false">No errors</option>
        </select>
      </div>

      <div className="filter-group">
        <label>Annotation</label>
        <select
          value={activeFilters.annotation_status || ''}
          onChange={e => setFilter('annotation_status', e.target.value)}
        >
          <option value="">All</option>
          {filters.annotation_statuses.map(s => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>

      <div className="filter-group">
        <label>Search</label>
        <input
          type="text"
          placeholder="keyword..."
          value={activeFilters.keyword || ''}
          onChange={e => setFilter('keyword', e.target.value)}
        />
      </div>

      {annotationProgress && (
        <div className="annotation-progress">
          <h4>Annotation Progress</h4>
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${(annotationProgress.annotated / Math.max(annotationProgress.total_sessions, 1)) * 100}%` }}
            />
          </div>
          <div className="progress-stats">
            <span>{annotationProgress.annotated}/{annotationProgress.total_sessions}</span>
            <span className="approved">{annotationProgress.approved} approved</span>
            <span className="rejected">{annotationProgress.rejected} rejected</span>
            <span className="flagged">{annotationProgress.flagged} flagged</span>
          </div>
        </div>
      )}
    </div>
  )
}
