import React, { useState, useEffect, useCallback } from 'react'
import { useStore } from '../store'
import { saveAnnotation, fetchAnnotations, fetchSessions } from '../api'

const CATEGORIES = [
  'coding', 'file_management', 'web_research', 'scheduling',
  'communication', 'data_analysis', 'system_maintenance',
  'content_creation', 'finance_crypto', 'memory_management',
  'agent_orchestration', 'other',
]

export default function AnnotationPanel() {
  const selectedSid = useStore(s => s.selectedSid)
  const sessionDetail = useStore(s => s.sessionDetail)
  const sessions = useStore(s => s.sessions)
  const selectSession = useStore(s => s.selectSession)

  const annotation = sessionDetail?.annotation
  const cls = sessionDetail?.classification || {}

  const [status, setStatus] = useState('')
  const [category, setCategory] = useState('')
  const [subcategory, setSubcategory] = useState('')
  const [confidence, setConfidence] = useState('')
  const [language, setLanguage] = useState('')
  const [notes, setNotes] = useState('')
  const [reviewer, setReviewer] = useState(() => localStorage.getItem('reviewer') || '')
  const [saving, setSaving] = useState(false)

  // Load annotation state when session changes
  useEffect(() => {
    if (annotation) {
      setStatus(annotation.status || '')
      setCategory(annotation.corrected_category || '')
      setSubcategory(annotation.corrected_subcategory || '')
      setConfidence(annotation.corrected_confidence || '')
      setLanguage(annotation.corrected_language || '')
      setNotes(annotation.notes || '')
      if (annotation.reviewer) setReviewer(annotation.reviewer)
    } else {
      setStatus('')
      setCategory('')
      setSubcategory('')
      setConfidence('')
      setLanguage('')
      setNotes('')
    }
  }, [annotation, selectedSid])

  const doSave = useCallback(async (overrideStatus) => {
    const s = overrideStatus || status
    if (!s || !selectedSid) return
    setSaving(true)
    localStorage.setItem('reviewer', reviewer)
    await saveAnnotation(selectedSid, {
      status: s,
      corrected_category: category || null,
      corrected_subcategory: subcategory || null,
      corrected_confidence: confidence || null,
      corrected_language: language || null,
      notes: notes || null,
      reviewer: reviewer || null,
    })
    // Refresh annotations
    const ann = await fetchAnnotations()
    useStore.getState().setAnnotations(ann.annotations, ann.progress)
    setSaving(false)
  }, [selectedSid, status, category, subcategory, confidence, language, notes, reviewer])

  const quickAction = useCallback((actionStatus) => {
    setStatus(actionStatus)
    doSave(actionStatus)
  }, [doSave])

  // Navigate to next unannotated session
  const goNext = useCallback(() => {
    const idx = sessions.findIndex(s => s.sid === selectedSid)
    for (let i = idx + 1; i < sessions.length; i++) {
      if (!sessions[i].annotation_status) {
        selectSession(sessions[i].sid)
        return
      }
    }
    // Wrap around
    for (let i = 0; i < idx; i++) {
      if (!sessions[i].annotation_status) {
        selectSession(sessions[i].sid)
        return
      }
    }
  }, [sessions, selectedSid, selectSession])

  const goPrev = useCallback(() => {
    const idx = sessions.findIndex(s => s.sid === selectedSid)
    if (idx > 0) selectSession(sessions[idx - 1].sid)
  }, [sessions, selectedSid, selectSession])

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return
      switch (e.key) {
        case 'a': quickAction('approved'); break
        case 'r': quickAction('rejected'); break
        case 'f': quickAction('flagged'); break
        case 'c': setStatus('corrected'); break
        case 'n': goNext(); break
        case 'p': goPrev(); break
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [quickAction, goNext, goPrev])

  return (
    <div className="annotation-panel">
      <div className="annotation-header">
        <h3>Annotation</h3>
        <div className="annotation-nav">
          <button className="btn btn-small" onClick={goPrev} title="Previous (p)">Prev</button>
          <button className="btn btn-small" onClick={goNext} title="Next unannotated (n)">Next</button>
        </div>
      </div>

      <div className="annotation-current">
        <div className="current-label">Current: <strong>{cls.primary_category}</strong> / {cls.subcategory}</div>
        <div className="current-intent">{cls.user_intent_summary}</div>
      </div>

      <div className="annotation-actions">
        <button className={`btn btn-approve ${status === 'approved' ? 'active' : ''}`} onClick={() => quickAction('approved')} title="(a)">
          Approve
        </button>
        <button className={`btn btn-reject ${status === 'rejected' ? 'active' : ''}`} onClick={() => quickAction('rejected')} title="(r)">
          Reject
        </button>
        <button className={`btn btn-flag ${status === 'flagged' ? 'active' : ''}`} onClick={() => quickAction('flagged')} title="(f)">
          Flag
        </button>
        <button className={`btn btn-correct ${status === 'corrected' ? 'active' : ''}`} onClick={() => setStatus('corrected')} title="(c)">
          Correct
        </button>
      </div>

      {status === 'corrected' && (
        <div className="correction-fields">
          <div className="field">
            <label>Category</label>
            <select value={category} onChange={e => setCategory(e.target.value)}>
              <option value="">-- keep original --</option>
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Subcategory</label>
            <input type="text" value={subcategory} onChange={e => setSubcategory(e.target.value)} placeholder="subcategory" />
          </div>
          <div className="field">
            <label>Confidence</label>
            <select value={confidence} onChange={e => setConfidence(e.target.value)}>
              <option value="">-- keep --</option>
              <option value="high">high</option>
              <option value="medium">medium</option>
              <option value="low">low</option>
            </select>
          </div>
          <div className="field">
            <label>Language</label>
            <select value={language} onChange={e => setLanguage(e.target.value)}>
              <option value="">-- keep --</option>
              <option value="zh">zh</option>
              <option value="en">en</option>
              <option value="mixed">mixed</option>
            </select>
          </div>
        </div>
      )}

      <div className="field">
        <label>Notes</label>
        <textarea value={notes} onChange={e => setNotes(e.target.value)} placeholder="Add notes..." rows={3} />
      </div>

      <div className="field">
        <label>Reviewer</label>
        <input type="text" value={reviewer} onChange={e => setReviewer(e.target.value)} placeholder="Your name" />
      </div>

      {status === 'corrected' && (
        <button className="btn btn-primary btn-save" onClick={() => doSave()} disabled={saving}>
          {saving ? 'Saving...' : 'Save Correction'}
        </button>
      )}

      <div className="keyboard-hints">
        <span><kbd>a</kbd> approve</span>
        <span><kbd>r</kbd> reject</span>
        <span><kbd>f</kbd> flag</span>
        <span><kbd>c</kbd> correct</span>
        <span><kbd>n</kbd> next</span>
        <span><kbd>p</kbd> prev</span>
      </div>
    </div>
  )
}
