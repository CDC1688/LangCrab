import React, { useEffect } from 'react'
import { useStore } from './store'
import { fetchFilters, fetchSummary, fetchSessions, fetchAnnotations } from './api'
import InnerGraph from './components/InnerGraph'
import SessionList from './components/SessionList'
import FilterSidebar from './components/FilterSidebar'
import StatePanel from './components/StatePanel'
import AnnotationPanel from './components/AnnotationPanel'
import Dashboard from './components/Dashboard'
import LogAnalysis from './components/LogAnalysis'
import ErrorReport from './components/ErrorReport'

export default function App() {
  const view = useStore(s => s.view)
  const breadcrumb = useStore(s => s.breadcrumb)
  const goToPipeline = useStore(s => s.goToPipeline)
  const goToSessions = useStore(s => s.goToSessions)
  const setView = useStore(s => s.setView)
  const selectedSid = useStore(s => s.selectedSid)
  const selectedNode = useStore(s => s.selectedNode)

  useEffect(() => {
    fetchFilters().then(f => useStore.getState().setFilters(f))
    fetchSummary().then(s => useStore.getState().setSummary(s))
    fetchAnnotations().then(d => useStore.getState().setAnnotations(d.annotations, d.progress))
  }, [])

  const activeFilters = useStore(s => s.activeFilters)
  const offset = useStore(s => s.offset)
  const limit = useStore(s => s.limit)
  useEffect(() => {
    fetchSessions(activeFilters, offset, limit).then(d => {
      useStore.getState().setSessions(d.items, d.total)
    })
  }, [activeFilters, offset, limit])

  return (
    <div className="app">
      <header className="header">
        <div className="header-left">
          <h1 onClick={goToPipeline} style={{ cursor: 'pointer' }}>
            OpenClaw Trace Viewer
          </h1>
          {breadcrumb.length > 0 && (
            <nav className="breadcrumb">
              {breadcrumb.map((item, i) => (
                <span key={i}>
                  <span className="breadcrumb-sep">/</span>
                  <span
                    className={i < breadcrumb.length - 1 ? 'breadcrumb-link' : 'breadcrumb-current'}
                    onClick={() => {
                      if (i === 0) goToPipeline()
                      else if (i === 1) goToSessions()
                    }}
                  >
                    {item}
                  </span>
                </span>
              ))}
            </nav>
          )}
        </div>
        <div className="header-nav">
          <button className={view === 'sessions' ? 'active' : ''} onClick={goToSessions}>Sessions</button>
          <button className={view === 'dashboard' ? 'active' : ''} onClick={() => setView('dashboard')}>Dashboard</button>
          <button className={view === 'logAnalysis' ? 'active' : ''} onClick={() => setView('logAnalysis')}>Log Analysis</button>
          <button className={view === 'errorReport' ? 'active' : ''} onClick={() => setView('errorReport')}>Error Report</button>
        </div>
      </header>

      <div className="main-layout">
        {(view === 'sessions' || view === 'session') && <FilterSidebar />}

        <div className="content">
          {view === 'sessions' && <SessionList />}
          {view === 'session' && <InnerGraph />}
          {view === 'dashboard' && <Dashboard />}
          {view === 'logAnalysis' && <LogAnalysis />}
          {view === 'errorReport' && <ErrorReport />}
        </div>

        {view === 'session' && selectedNode && <StatePanel />}
        {view === 'session' && selectedSid && <AnnotationPanel />}
      </div>
    </div>
  )
}
