import React, { useEffect, useState } from 'react'
import { useStore } from '../store'
import { fetchSessions, fetchSession } from '../api'

const CAT_CN = {
  coding: '编程开发', communication: '通讯交流', content_creation: '内容创作',
  data_analysis: '数据分析', file_management: '文件管理', finance_crypto: '金融加密',
  memory_management: '记忆管理', other: '其他', system_maintenance: '系统维护',
  web_research: '网络搜索', scheduling: '任务调度', agent_orchestration: '代理编排',
}

export default function LogAnalysis() {
  const filters = useStore(s => s.filters)
  const logAnalysisSid = useStore(s => s.logAnalysisSid)

  const [sessions, setSessions] = useState([])
  const [total, setTotal] = useState(0)
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)

  // Filters
  const [fSid, setFSid] = useState('')
  const [fCat, setFCat] = useState('')
  const [fSubcat, setFSubcat] = useState('')
  const [fModel, setFModel] = useState('')
  const [fIntent, setFIntent] = useState('')
  const [fError, setFError] = useState('')

  // Load sessions
  useEffect(() => {
    const f = { keyword: fIntent || fSid || undefined, category: fCat || undefined, subcategory: fSubcat || undefined, model: fModel || undefined }
    if (fError === 'true') f.has_errors = true
    if (fError === 'false') f.has_errors = false
    fetchSessions(f, 0, 500).then(d => {
      setSessions(d.items)
      setTotal(d.total)
    })
  }, [fSid, fCat, fSubcat, fModel, fIntent, fError])

  // Auto-select from cross-link
  useEffect(() => {
    if (logAnalysisSid) {
      handleSelect(logAnalysisSid)
      useStore.getState().setLogAnalysisSid(null)
    }
  }, [logAnalysisSid])

  const handleSelect = (sid) => {
    setSelected(sid)
    fetchSession(sid).then(d => setDetail(d))
  }

  const goTrace = (sid) => {
    useStore.getState().selectSession(sid)
  }

  return (
    <div className="la-page">
      <div className="la-header">
        <h2>LangGraph Agent 日志分析</h2>
        <span className="la-count">共 {total} 条记录</span>
      </div>
      <div className="la-filters">
        <input placeholder="搜索 SID" value={fSid} onChange={e => setFSid(e.target.value)} />
        <select value={fCat} onChange={e => { setFCat(e.target.value); setFSubcat('') }}>
          <option value="">全部分类</option>
          {(filters?.categories || []).map(c => <option key={c} value={c}>{CAT_CN[c] || c}</option>)}
        </select>
        <select value={fSubcat} onChange={e => setFSubcat(e.target.value)}>
          <option value="">全部子分类</option>
          {(filters?.subcategories || []).map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={fModel} onChange={e => setFModel(e.target.value)}>
          <option value="">全部模型</option>
          {(filters?.models || []).map(m => <option key={m} value={m}>{m}</option>)}
        </select>
        <input placeholder="意图关键词" value={fIntent} onChange={e => setFIntent(e.target.value)} />
        <select value={fError} onChange={e => setFError(e.target.value)}>
          <option value="">全部</option>
          <option value="true">有错误</option>
          <option value="false">无错误</option>
        </select>
      </div>
      <div className="la-container">
        {/* Left: session list */}
        <div className="la-list">
          {sessions.map(s => (
            <div
              key={s.sid}
              className={`la-item ${selected === s.sid ? 'active' : ''}`}
              onClick={() => handleSelect(s.sid)}
            >
              <div>
                <span className="la-cat">[{CAT_CN[s.primary_category] || s.primary_category}]</span>
                {' '}
                <span className="la-time">{s.event_time}</span>
              </div>
              <div className="la-intent">{s.user_intent_summary}</div>
            </div>
          ))}
          {sessions.length === 0 && <p className="la-empty">没有匹配的记录</p>}
        </div>

        {/* Right: detail */}
        <div className="la-detail">
          {!detail && <p className="la-empty">← 请选择一条记录查看详情</p>}
          {detail && <DetailPanel detail={detail} onGoTrace={goTrace} />}
        </div>
      </div>
    </div>
  )
}

function DetailPanel({ detail, onGoTrace }) {
  const cls = detail.classification || {}
  const inner = detail.inner_graph
  const t = cls.token_usage || {}
  const errs = cls.error_types || []
  const tools = cls.tool_names_used || []
  const errRate = cls.error_rate != null ? (cls.error_rate * 100).toFixed(1) + '%' : 'N/A'
  const boolCn = v => v ? <span className="bool-yes">是</span> : <span className="bool-no">否</span>

  return (
    <div className="la-detail-content">
      <button className="btn btn-primary btn-small la-trace-btn" onClick={() => onGoTrace(cls.sid)}>
        View Trace →
      </button>

      <h3>1. 会话基础信息</h3>
      <ul>
        <li><b>会话 ID：</b><span className="la-sid">{cls.sid}</span></li>
        <li><b>关联账号：</b>{cls.account}</li>
        <li><b>模型版本：</b>{cls.model}</li>
        <li><b>事件时间：</b>{cls.event_time}</li>
        <li><b>来源文件：</b>{cls.source_file || 'N/A'}</li>
        <li><b>消息总数：</b>{cls.num_messages} 条</li>
      </ul>

      <h3>2. 分类与意图信息</h3>
      <ul>
        <li><b>主分类：</b>{CAT_CN[cls.primary_category] || cls.primary_category}（{cls.primary_category}）</li>
        <li><b>子分类：</b>{cls.subcategory}</li>
        <li><b>用户意图：</b>{cls.user_intent_summary}</li>
        <li><b>语言类型：</b>{cls.language}</li>
        <li><b>分类可信度：</b>{cls.confidence}</li>
      </ul>

      <h3>3. 执行特征</h3>
      <ul>
        <li><b>是否由定时任务触发：</b>{boolCn(cls.is_cron_triggered)}</li>
        <li><b>是否启用子代理：</b>{boolCn(cls.is_subagent)}</li>
        <li><b>迭代次数：</b>{cls.iterations} 次</li>
        <li><b>是否发生错误：</b>{boolCn(cls.had_errors)}</li>
        <li><b>是否通过规则直接分类：</b>{boolCn(cls.heuristic_classified)}</li>
        <li><b>结束原因：</b>{cls.finish_reason || 'N/A'}</li>
        <li><b>工具调用成功数：</b>{cls.tool_success_count ?? 'N/A'}</li>
        <li><b>工具调用失败数：</b>{cls.tool_error_count ?? 'N/A'}</li>
        <li><b>错误率：</b>{errRate}</li>
        <li><b>最大连续错误数：</b>{cls.consecutive_error_max ?? 'N/A'}</li>
        <li><b>错误类型：</b>{errs.length ? errs.join(', ') : '无'}</li>
        {t.total_tokens > 0 && (
          <li><b>Token 用量：</b>prompt {t.prompt_tokens} / completion {t.completion_tokens} / 总计 {t.total_tokens}</li>
        )}
      </ul>

      <h3>4. 调用工具列表</h3>
      <p>共使用 <b>{tools.length}</b> 类工具：</p>
      <div className="la-tools">{tools.map(t => <span key={t} className="la-tag">{t}</span>)}</div>

      {/* Section 5: Inner Graph Details */}
      {inner ? <InnerGraphDetail inner={inner} /> : (
        <><h3>5. 分类过程详情（Inner Graph）</h3><p className="la-empty">无详细数据</p></>
      )}
    </div>
  )
}

function InnerGraphDetail({ inner }) {
  const inp = inner.input || {}
  const res = inner.result || {}
  const loop = inner.loop || {}
  const msgs = inner.message_history || []

  let triggerDesc = inp.is_cron_triggered ? '由定时任务触发' : '非定时任务触发'
  triggerDesc += inp.is_subagent ? '，启用子代理' : '，未启用子代理'

  // Parse classification attempts from message_history
  const attempts = []
  msgs.forEach((msg, idx) => {
    if (msg.role === 'human' && (msg.content || '').startsWith('Classification attempt')) {
      const jsonMatch = (msg.content || '').match(/\{[\s\S]*\}/)
      let parsed = null
      if (jsonMatch) { try { parsed = JSON.parse(jsonMatch[0]) } catch (e) {} }
      const nextMsg = msgs[idx + 1]
      const isFail = nextMsg && nextMsg.role === 'human' && (nextMsg.content || '').includes('failed validation')
      let validationErrors = []
      if (isFail && nextMsg.content) {
        validationErrors = nextMsg.content.split('\n').filter(l => l.trim().startsWith('- ')).map(l => l.trim().slice(2))
      }
      attempts.push({ parsed, isFail, validationErrors })
    }
  })

  return (
    <>
      <h3>5. 分类过程详情（Inner Graph）</h3>

      <h4 className="la-sub">一、会话输入信息</h4>
      <ul>
        <li><b>触发方式：</b>{triggerDesc}</li>
        <li><b>消息统计：</b>共 {inp.num_messages ?? 0} 条消息，其中用户消息 {inp.num_user_messages ?? 0} 条</li>
        <li><b>调用工具：</b>{(inp.tool_names_used || []).length ? (inp.tool_names_used || []).join(', ') : '无工具调用记录'}</li>
      </ul>

      <h4 className="la-sub">二、用户交互内容</h4>
      {inp.user_messages_text
        ? <pre className="la-msg-block">{inp.user_messages_text}</pre>
        : <p className="la-empty">无用户消息记录</p>
      }
      {inp.system_prompt_summary && (
        <>
          <h4 className="la-sub">系统提示词摘要</h4>
          <pre className="la-msg-block">{inp.system_prompt_summary}</pre>
        </>
      )}

      <h4 className="la-sub">三、分类迭代过程</h4>
      {loop.heuristic_classified || (msgs.length === 0 && loop.iterations === 0) ? (
        <p className="la-muted">通过启发式规则直接分类，无 LLM 迭代过程</p>
      ) : (
        <>
          <p className="la-muted">通过 <b>LLM 调用</b>进行分类，共迭代 <b>{loop.iterations}</b> 次</p>
          {attempts.map((a, i) => (
            <div key={i} className={`la-attempt ${a.isFail ? 'fail' : 'pass'}`}>
              <div className="la-attempt-label">
                第 {i + 1} 次分类尝试 {a.isFail ? '❌ 未通过' : '✅ 通过'}
              </div>
              {a.parsed && (
                <ul>
                  <li><b>主分类：</b>{CAT_CN[a.parsed.primary_category] || a.parsed.primary_category}</li>
                  <li><b>子分类：</b>{a.parsed.subcategory || 'N/A'}</li>
                  <li><b>意图摘要：</b>{a.parsed.user_intent_summary || ''}</li>
                  <li><b>语言：</b>{a.parsed.language || 'N/A'}</li>
                  <li><b>置信度：</b>{a.parsed.confidence || 'N/A'}</li>
                </ul>
              )}
              {a.isFail && a.validationErrors.length > 0 && (
                <div className="la-attempt fail" style={{marginTop: 4}}>
                  <div className="la-attempt-label">验证失败原因</div>
                  <ul>{a.validationErrors.map((e, j) => <li key={j}>{e}</li>)}</ul>
                </div>
              )}
            </div>
          ))}
        </>
      )}

      <h4 className="la-sub">四、最终分类结果</h4>
      <ul>
        <li><b>主分类：</b>{CAT_CN[res.primary_category] || res.primary_category || 'N/A'}</li>
        <li><b>子分类：</b>{res.subcategory || 'N/A'}</li>
        <li><b>用户意图：</b>{res.user_intent_summary || 'N/A'}</li>
        <li><b>语言类型：</b>{res.language || 'N/A'}</li>
        <li><b>分类可信度：</b>{res.confidence || 'N/A'}</li>
      </ul>

      <h4 className="la-sub">五、会话处理特征</h4>
      <ul>
        <li><b>迭代次数：</b>{loop.iterations ?? 'N/A'} 次{loop.iterations > 1 ? '（首次分类失败后自动重试）' : ''}</li>
        <li><b>错误记录：</b>{loop.had_errors ? '有执行错误' : '无执行错误'}</li>
        <li><b>分类方式：</b>{loop.heuristic_classified ? '通过启发式规则直接分类' : '需经过 LLM 分析与校验流程'}</li>
      </ul>
    </>
  )
}
