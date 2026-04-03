import React, { useEffect, useState } from 'react'
import { useStore } from '../store'

const CAT_CN = {
  coding: '编程开发', communication: '通讯交流', content_creation: '内容创作',
  data_analysis: '数据分析', file_management: '文件管理', finance_crypto: '金融加密',
  memory_management: '记忆管理', other: '其他', system_maintenance: '系统维护',
  web_research: '网络搜索', scheduling: '任务调度', agent_orchestration: '代理编排',
}

export default function ErrorReport() {
  const filters = useStore(s => s.filters)

  const [sessions, setSessions] = useState([])
  const [total, setTotal] = useState(0)
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)

  // Filters
  const [fSid, setFSid] = useState('')
  const [fModel, setFModel] = useState('')
  const [fErrType, setFErrType] = useState('')
  const [fRecovered, setFRecovered] = useState('')
  const [fLoop, setFLoop] = useState('')
  const [fCat, setFCat] = useState('')

  // Collect error types from loaded data
  const [errorTypes, setErrorTypes] = useState([])

  useEffect(() => {
    const params = new URLSearchParams()
    if (fModel) params.set('model', fModel)
    if (fErrType) params.set('error_type', fErrType)
    if (fRecovered) params.set('recovered', fRecovered)
    if (fLoop) params.set('error_loop', fLoop)
    if (fCat) params.set('category', fCat)
    if (fSid) params.set('keyword', fSid)

    fetch(`/api/error-sessions?${params}`)
      .then(r => r.json())
      .then(d => {
        setSessions(d.items)
        setTotal(d.total)
        // Collect all error types
        const types = new Set()
        d.items.forEach(s => (s.error_types || []).forEach(t => types.add(t)))
        setErrorTypes([...types].sort())
      })
  }, [fSid, fModel, fErrType, fRecovered, fLoop, fCat])

  const handleSelect = (session) => {
    setSelected(session.sid)
    setDetail(session)
  }

  const goTrace = (sid) => {
    useStore.getState().selectSession(sid)
  }

  return (
    <div className="er-page">
      <div className="er-header">
        <h2>错误报告 - LangGraph Agent 日志分析</h2>
        <span className="er-count">共 {total} 条错误记录</span>
      </div>
      <div className="er-filters">
        <input placeholder="搜索 SID" value={fSid} onChange={e => setFSid(e.target.value)} />
        <select value={fModel} onChange={e => setFModel(e.target.value)}>
          <option value="">全部模型</option>
          {(filters?.models || []).map(m => <option key={m} value={m}>{m}</option>)}
        </select>
        <select value={fErrType} onChange={e => setFErrType(e.target.value)}>
          <option value="">全部错误类型</option>
          {errorTypes.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={fRecovered} onChange={e => setFRecovered(e.target.value)}>
          <option value="">全部</option>
          <option value="true">已恢复</option>
          <option value="false">未恢复</option>
        </select>
        <select value={fLoop} onChange={e => setFLoop(e.target.value)}>
          <option value="">全部</option>
          <option value="true">有错误循环</option>
          <option value="false">无错误循环</option>
        </select>
        <select value={fCat} onChange={e => setFCat(e.target.value)}>
          <option value="">全部分类</option>
          {(filters?.categories || []).map(c => <option key={c} value={c}>{CAT_CN[c] || c}</option>)}
        </select>
      </div>
      <div className="er-container">
        {/* Left: error session list */}
        <div className="er-list">
          {sessions.map(s => (
            <div
              key={s.sid}
              className={`er-item ${selected === s.sid ? 'active' : ''}`}
              onClick={() => handleSelect(s)}
            >
              <div>
                <span className="er-err-count">[{s.tool_error_count} 个错误]</span>
                {' '}
                <span className="er-time">{s.event_time}</span>
                <span className={`er-badge ${s.error_report?.agent_recovered ? 'recovered' : ''}`}>
                  {s.error_report?.agent_recovered ? '已恢复' : '未恢复'}
                </span>
              </div>
              <div className="er-intent">{s.user_intent_summary} ({s.model})</div>
            </div>
          ))}
          {sessions.length === 0 && <p className="er-empty">没有匹配的错误记录</p>}
        </div>

        {/* Right: detail */}
        <div className="er-detail">
          {!detail && <p className="er-empty">← 请选择一条错误记录查看详情</p>}
          {detail && <ErrorDetailPanel detail={detail} onGoTrace={goTrace} />}
        </div>
      </div>
    </div>
  )
}

function ErrorDetailPanel({ detail, onGoTrace }) {
  const cls = detail
  const err = detail.error_report || {}
  const t = cls.token_usage || {}
  const tools = cls.tool_names_used || []
  const toolErrors = err.tool_errors || []
  const errRate = cls.error_rate != null ? (cls.error_rate * 100).toFixed(1) + '%' : 'N/A'
  const boolCn = v => v ? <span className="bool-yes">是</span> : <span className="bool-no">否</span>

  return (
    <div className="er-detail-content">
      <button className="btn btn-primary btn-small er-trace-btn" onClick={() => onGoTrace(cls.sid)}>
        View Trace →
      </button>

      <h3>1. 会话基础信息</h3>
      <ul>
        <li><b>会话 ID：</b><span className="er-sid">{cls.sid}</span></li>
        <li><b>关联账号：</b>{cls.account}</li>
        <li><b>模型版本：</b>{cls.model}</li>
        <li><b>事件时间：</b>{cls.event_time}</li>
        <li><b>来源文件：</b>{cls.source_file || 'N/A'}</li>
        <li><b>消息总数：</b>{cls.num_messages} 条</li>
        <li><b>主分类：</b>{CAT_CN[cls.primary_category] || cls.primary_category}</li>
        <li><b>子分类：</b>{cls.subcategory}</li>
        <li><b>用户意图：</b>{cls.user_intent_summary}</li>
        <li><b>结束原因：</b>{cls.finish_reason || 'N/A'}</li>
      </ul>

      <h3>2. 错误概览</h3>
      <div className="er-stat-bar">
        <div className="er-stat"><div className="er-stat-num red">{cls.tool_error_count}</div><div className="er-stat-label">错误次数</div></div>
        <div className="er-stat"><div className="er-stat-num green">{cls.tool_success_count}</div><div className="er-stat-label">成功次数</div></div>
        <div className="er-stat"><div className="er-stat-num red">{errRate}</div><div className="er-stat-label">错误率</div></div>
        <div className="er-stat"><div className="er-stat-num orange">{cls.consecutive_error_max}</div><div className="er-stat-label">最大连续错误</div></div>
      </div>
      <ul>
        <li><b>Agent 是否恢复：</b>{err.agent_recovered ? <span className="bool-no">是，已恢复</span> : <span className="bool-yes">否，未恢复</span>}</li>
        <li><b>是否检测到错误循环：</b>{boolCn(err.error_loop_detected)}</li>
        <li><b>错误类型：</b>{(cls.error_types || []).join(', ') || '无'}</li>
      </ul>

      <h3>3. 错误详情（{toolErrors.length} 条）</h3>
      {toolErrors.map((te, i) => (
        <div key={i} className="er-error-card">
          <div className={`er-card-header ${te.recovered ? 'recovered' : 'not-recovered'}`}>
            <span>错误 #{i + 1}：工具 <b>{te.tool}</b></span>
            <span>{te.recovered ? '✅ 已恢复' : '❌ 未恢复'}</span>
          </div>
          <div className="er-card-body">
            <div><b>错误类型：</b>{te.error_type}</div>
            <div style={{ marginTop: 6 }}><b>错误信息：</b></div>
            <pre className="er-error-pre">{te.error_text}</pre>
            <div className="er-meta">消息位置：第 {te.position} 条</div>
          </div>
        </div>
      ))}

      <h3>4. 用户交互内容</h3>
      {err.user_messages_text
        ? <pre className="er-msg-block">{err.user_messages_text}</pre>
        : <p className="er-empty">无用户消息记录</p>
      }

      {err.system_prompt_summary && (
        <>
          <h3>5. 系统提示词摘要</h3>
          <pre className="er-msg-block">{err.system_prompt_summary}</pre>
        </>
      )}

      <h3>6. 调用工具列表</h3>
      <p>共使用 <b>{tools.length}</b> 类工具：</p>
      <div className="er-tools">{tools.map(t => <span key={t} className="er-tag">{t}</span>)}</div>

      {t.total_tokens > 0 && (
        <>
          <h3>7. Token 用量</h3>
          <ul>
            <li><b>Prompt：</b>{t.prompt_tokens || 'N/A'}</li>
            <li><b>Completion：</b>{t.completion_tokens || 'N/A'}</li>
            <li><b>总计：</b>{t.total_tokens || 'N/A'}</li>
          </ul>
        </>
      )}
    </div>
  )
}
