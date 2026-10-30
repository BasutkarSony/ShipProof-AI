import React, { useEffect, useState, useMemo } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

// Professional Inline SVGs
const CheckIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <polyline points="20 6 9 17 4 12" />
  </svg>
)

const AlertIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
)

const ArrowIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <line x1="5" y1="12" x2="19" y2="12" />
    <polyline points="12 5 19 12 12 19" />
  </svg>
)

const LockIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
  </svg>
)

const SearchIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="8" />
    <line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
)

const ShieldIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
  </svg>
)

export default function App() {
  const [orders, setOrders] = useState([])
  const [results, setResults] = useState({})
  const [aiResults, setAiResults] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [paypal, setPaypal] = useState({ loading: true })
  const [oauthTesting, setOauthTesting] = useState(false)
  const [oauthVerified, setOauthVerified] = useState(false)
  const [oauthMessage, setOauthMessage] = useState('')

  // UI state
  const [activeTab, setActiveTab] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [showArchDetails, setShowArchDetails] = useState(false)
  const [batchAiLoading, setBatchAiLoading] = useState(false)
  const [batchValidateLoading, setBatchValidateLoading] = useState(false)
  const [copiedPayload, setCopiedPayload] = useState(false)

  // Drawer & Remediation state
  const [selectedOrder, setSelectedOrder] = useState(null)
  const [remediationForm, setRemediationForm] = useState({
    tracking_number: '',
    carrier: '',
    amount: '',
    signature_obtained: false,
    evidence_text: ''
  })
  const [inspectLoading, setInspectLoading] = useState(false)

  useEffect(() => {
    fetch('http://127.0.0.1:8000/api/orders')
      .then(r => {
        if (!r.ok) throw new Error('Could not load shipments')
        return r.json()
      })
      .then(data => {
        setOrders(data.orders || [])
      })
      .catch(() => setError('Cannot connect to the backend. Make sure it is running on port 8000.'))
      .finally(() => setLoading(false))

    fetch('http://127.0.0.1:8000/api/paypal/status')
      .then(r => {
        if (!r.ok) throw new Error('Could not load PayPal status')
        return r.json()
      })
      .then(data => setPaypal(data))
      .catch(() => setPaypal({ error: 'PayPal status unavailable' }))
  }, [])

  // Validate a single order
  async function validate(order) {
    setResults(old => ({ ...old, [order.order_id]: { loading: true } }))
    try {
      const response = await fetch('http://127.0.0.1:8000/api/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(order)
      })
      if (!response.ok) throw new Error('Validation failed')
      const data = await response.json()
      setResults(old => ({ ...old, [order.order_id]: data }))
      return data
    } catch {
      const err = { error: 'Validation failed. Check the backend.' }
      setResults(old => ({ ...old, [order.order_id]: err }))
      return err
    }
  }

  // AI evidence analysis
  async function analyzeOrderEvidence(order) {
    setAiResults(old => ({ ...old, [order.order_id]: { loading: true } }))
    try {
      const response = await fetch('http://127.0.0.1:8000/api/analyze-evidence', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(order)
      })
      if (!response.ok) throw new Error('AI analysis failed')
      const data = await response.json()
      setAiResults(old => ({ ...old, [order.order_id]: data }))
      return data
    } catch {
      const errObj = { error: 'AI evidence analysis failed. Check the backend.' }
      setAiResults(old => ({ ...old, [order.order_id]: errObj }))
      return errObj
    }
  }

  // Batch actions
  async function handleValidateAll() {
    setBatchValidateLoading(true)
    for (const order of orders) {
      await validate(order)
    }
    setBatchValidateLoading(false)
  }

  async function handleAnalyzeAll() {
    setBatchAiLoading(true)
    for (const order of orders) {
      await analyzeOrderEvidence(order)
    }
    setBatchAiLoading(false)
  }

  // Verify PayPal Sandbox connection via OAuth token exchange without submitting data
  async function testPayPalConnection() {
    setOauthTesting(true)
    try {
      const res = await fetch('http://127.0.0.1:8000/api/paypal/verify-connection', { method: 'POST' })
      const data = await res.json()
      if (res.ok && data.success) {
        setOauthVerified(true)
        setOauthMessage('OAuth 2.0 Authenticated · Write Gate Locked')
      } else {
        setOauthVerified(false)
        setOauthMessage(data.detail || 'PayPal OAuth verification failed')
      }
    } catch {
      setOauthVerified(false)
      setOauthMessage('Unable to reach backend PayPal verification endpoint')
    } finally {
      setOauthTesting(false)
    }
  }

  // Open Drawer and populate remediation form
  function openInspector(order) {
    setSelectedOrder(order)
    setRemediationForm({
      tracking_number: order.tracking_number || '',
      carrier: order.carrier || 'FEDEX',
      carrier_name_other: order.carrier_name_other || '',
      status: order.status || 'DELIVERED',
      amount: order.amount !== undefined ? order.amount : '',
      signature_obtained: Boolean(order.signature_obtained),
      evidence_text: order.evidence_text || ''
    })
    setCopiedPayload(false)

    // Run both checks if not already cached
    if (!aiResults[order.order_id]) {
      setInspectLoading(true)
      analyzeOrderEvidence(order).finally(() => setInspectLoading(false))
    }
    if (!results[order.order_id]) {
      validate(order)
    }
  }

  // Re-run analysis with remediation form inputs
  async function handleRemediationSubmit() {
    if (!selectedOrder) return
    setInspectLoading(true)

    const updatedOrder = {
      ...selectedOrder,
      tracking_number: remediationForm.tracking_number,
      carrier: remediationForm.carrier,
      carrier_name_other: remediationForm.carrier === 'OTHER' ? remediationForm.carrier_name_other : '',
      status: remediationForm.status || selectedOrder.status || 'SHIPPED',
      amount: remediationForm.amount !== '' ? parseFloat(remediationForm.amount) : 0,
      signature_obtained: remediationForm.signature_obtained,
      evidence_text: remediationForm.evidence_text
    }

    // Update in local orders array
    setOrders(prev => prev.map(o => o.order_id === updatedOrder.order_id ? updatedOrder : o))
    setSelectedOrder(updatedOrder)

    // Re-run both validation and AI analysis
    await Promise.all([
      validate(updatedOrder),
      analyzeOrderEvidence(updatedOrder)
    ])

    setInspectLoading(false)
  }

  // Copy PayPal JSON payload
  function copyPayload(payload) {
    if (!payload) return
    navigator.clipboard.writeText(JSON.stringify(payload, null, 2))
    setCopiedPayload(true)
    setTimeout(() => setCopiedPayload(false), 2000)
  }

  // Calculations for stats
  const validatedCount = Object.values(results).filter(r => !r.loading && !r.error)
  const readyChecksCount = validatedCount.filter(r => r.result === 'PASS').length
  const blockedCount = validatedCount.filter(r => r.result === 'BLOCKED').length

  const aiList = Object.values(aiResults).filter(r => !r.loading && !r.error)
  const protectionReadyCount = aiList.filter(r => r.protection_tier === 'FULL_PROTECTION_READY').length

  // Filtered orders list
  const filteredOrders = useMemo(() => {
    return orders.filter(order => {
      const q = searchQuery.toLowerCase().trim()
      const matchesSearch =
        !q ||
        order.order_id?.toLowerCase().includes(q) ||
        order.transaction_id?.toLowerCase().includes(q) ||
        order.tracking_number?.toLowerCase().includes(q) ||
        order.shipping_address?.toLowerCase().includes(q) ||
        order.carrier?.toLowerCase().includes(q)

      if (!matchesSearch) return false

      const res = results[order.order_id]
      const ai = aiResults[order.order_id]

      if (activeTab === 'needs-remediation') {
        return (res && res.result === 'BLOCKED') || (ai && (ai.protection_tier === 'CRITICAL_DEFECT' || ai.protection_tier === 'EVIDENCE_INCOMPLETE'))
      }
      if (activeTab === 'protection-ready') {
        return ai && ai.protection_tier === 'FULL_PROTECTION_READY'
      }
      if (activeTab === 'delivered') {
        return order.status === 'DELIVERED'
      }

      return true
    })
  }, [orders, results, aiResults, activeTab, searchQuery])

  const currentAiResult = selectedOrder ? aiResults[selectedOrder.order_id] : null
  const currentValidation = selectedOrder ? results[selectedOrder.order_id] : null

  return (
    <div className="app-shell">
      {/* Sidebar Navigation */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">S</div>
          <div className="brand-title">
            <strong>ShipProof AI</strong>
            <small>PAYPAL EVIDENCE CONTROL</small>
          </div>
        </div>

        <div className="nav-section">Merchant Workspace</div>
        <div className="nav-item active">
          <span>▦</span>
          <span>Shipment Review</span>
          <span className="nav-badge">{orders.length}</span>
        </div>

        <div className="side-card">
          <div className="side-card-header">
            <span className="pulse"></span>
            <span>Policy Engine Active</span>
          </div>
          <div className="side-card-body">
            Deterministic NLP heuristics evaluate shipments against official PayPal Seller Protection guidelines.
          </div>
        </div>

        <div className="sidebar-footer">
          <strong>PAYPAL AI HACKATHON 2026</strong>
          <p>Pre-submission verification · Zero-hallucination compliance · Safe sandbox tracking.</p>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="main">
        {/* Topbar */}
        <header className="topbar">
          <div className="breadcrumb">
            <span>Workspace</span>
            <span>/</span>
            <strong>Shipment Evidence Queue</strong>
          </div>

          <div className="topbar-actions">
            <button
              className="pill-status"
              onClick={testPayPalConnection}
              disabled={oauthTesting}
              title="Click to test live PayPal Sandbox OAuth 2.0 authentication"
            >
              <span className={`pulse ${oauthVerified ? '' : 'warn'}`}></span>
              <span>
                {oauthTesting
                  ? 'Testing Sandbox Auth…'
                  : oauthVerified
                  ? oauthMessage
                  : paypal.configured
                  ? 'PayPal Sandbox: Authenticate ↗'
                  : 'PayPal Sandbox: Not Configured'}
              </span>
            </button>
            <div className="pill-status">
              <span style={{ color: '#275619', fontWeight: 700 }}>Write Gate: Locked</span>
            </div>
          </div>
        </header>

        {/* Hero Banner */}
        <section className="hero">
          <div className="hero-copy">
            <div className="eyebrow">
              <span>●</span> PRE-SUBMISSION SHIPMENT EVIDENCE & SELLER PROTECTION
            </div>
            <h1>
              Proof before
              <br />
              <span>you submit.</span>
            </h1>
            <p>
              Catch missing tracking numbers, invalid transit chronology, carrier mismatches, and $750+ high-value signature
              omissions before transmitting shipping evidence to PayPal Sandbox.
            </p>
          </div>

          <div className="hero-art-card">
            <div className="art-shield">
              <div className="shield-icon">
                <ShieldIcon />
              </div>
              <div>
                <strong>Seller Protection</strong>
                <small>Evidence Pre-Screening</small>
              </div>
            </div>
            <div className="art-lines">
              <span></span>
              <span></span>
              <span></span>
            </div>
            <div className="art-tag">AUDITABLE RULE-BASED NLP</div>
          </div>
        </section>

        {/* Engine Transparency & Architecture Disclosure */}
        <section className="architecture-banner">
          <div className="arch-info">
            <div className="arch-badge">AUDITABLE ENGINE</div>
            <div className="arch-text">
              <strong>Deterministic NLP & PayPal Policy Rules Engine</strong>
              <p>
                Zero-hallucination compliance architecture: evaluates carrier tracking regexes, milestone timelines, destination matching, and PayPal's $750+ signature threshold.
              </p>
            </div>
          </div>
          <button
            className="arch-criteria-toggle"
            onClick={() => setShowArchDetails(prev => !prev)}
          >
            {showArchDetails ? 'Hide criteria ▲' : 'View 5 core criteria ▼'}
          </button>
        </section>

        {showArchDetails && (
          <div className="arch-details-drawer">
            <strong>Evaluated Seller Protection & Data Quality Checks:</strong>
            <div className="arch-grid">
              <div className="arch-card">
                <strong>1. Carrier Pattern Verification</strong>
                Detects format consistency for UPS (1Z), FedEx, USPS (9x), DHL, and warns on carrier mismatch.
              </div>
              <div className="arch-card">
                <strong>2. High-Value $750+ Signature</strong>
                Checks if orders ≥ $750 USD include verified signature confirmation required by PayPal.
              </div>
              <div className="arch-card">
                <strong>3. Transit Chronology</strong>
                Verifies dispatch and delivery milestones (disallows delivery prior to shipment or in the future).
              </div>
              <div className="arch-card">
                <strong>4. Proof of Delivery / Destination</strong>
                Matches recipient city/postal-code tokens against carrier delivery scan notes.
              </div>
              <div className="arch-card">
                <strong>5. Exception Extraction</strong>
                Flags negative signals: returned to sender, damaged in transit, undeliverable, or failed delivery.
              </div>
            </div>
          </div>
        )}

        {/* Operational Metrics Cards */}
        <section className="stats-grid">
          <div className="stat-card">
            <span>SHIPMENTS IN QUEUE</span>
            <strong>{orders.length.toString().padStart(2, '0')}</strong>
            <small>Active workspace shipments</small>
          </div>
          <div className="stat-card">
            <span>DATA-QUALITY VALIDATED</span>
            <strong className="green">{readyChecksCount.toString().padStart(2, '0')}</strong>
            <small>Passed preliminary schema checks</small>
          </div>
          <div className="stat-card">
            <span>NEEDS REMEDIATION</span>
            <strong className={blockedCount > 0 ? 'red' : ''}>{blockedCount.toString().padStart(2, '0')}</strong>
            <small>Blocked data or milestone defects</small>
          </div>
          <div className="stat-card">
            <span>PROTECTION READY</span>
            <strong className="green">{protectionReadyCount.toString().padStart(2, '0')}</strong>
            <small>Full Seller Protection defense viability</small>
          </div>
        </section>

        {/* Queue Control Header */}
        <section className="queue-header">
          <div className="queue-title">
            <div className="eyebrow">SHIPMENT QUEUE</div>
            <h2>Evidence Verification Queue</h2>
            <p>Review individual shipments, inspect Seller Protection criteria, or remediate missing evidence.</p>
          </div>

          <div style={{ display: 'flex', gap: '10px' }}>
            <button
              className="btn-secondary btn-ai"
              onClick={handleAnalyzeAll}
              disabled={loading || batchAiLoading || !orders.length}
            >
              {batchAiLoading ? 'Analyzing AI…' : 'Scan All AI Evidence ↗'}
            </button>
            <button
              className="btn-primary"
              onClick={handleValidateAll}
              disabled={loading || batchValidateLoading || !orders.length}
            >
              {batchValidateLoading ? 'Validating…' : 'Run All Data Checks ↗'}
            </button>
          </div>
        </section>

        {error && <div className="findings-box issues" style={{ marginBottom: '20px' }}>{error}</div>}

        {/* Filter and Search Bar */}
        <div className="filter-bar">
          <div className="filter-tabs">
            <button
              className={`filter-tab ${activeTab === 'all' ? 'active' : ''}`}
              onClick={() => setActiveTab('all')}
            >
              All Shipments <span>{orders.length}</span>
            </button>
            <button
              className={`filter-tab ${activeTab === 'needs-remediation' ? 'active' : ''}`}
              onClick={() => setActiveTab('needs-remediation')}
            >
              Needs Remediation <span>{blockedCount}</span>
            </button>
            <button
              className={`filter-tab ${activeTab === 'protection-ready' ? 'active' : ''}`}
              onClick={() => setActiveTab('protection-ready')}
            >
              Protection Ready <span>{protectionReadyCount}</span>
            </button>
            <button
              className={`filter-tab ${activeTab === 'delivered' ? 'active' : ''}`}
              onClick={() => setActiveTab('delivered')}
            >
              Delivered <span>{orders.filter(o => o.status === 'DELIVERED').length}</span>
            </button>
          </div>

          <div className="search-input-wrap">
            <span className="search-icon">
              <SearchIcon />
            </span>
            <input
              type="text"
              className="search-input"
              placeholder="Search by order, txn, carrier..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
            />
          </div>
        </div>

        {/* Orders Queue Cards */}
        {loading ? (
          <div className="order-card" style={{ textAlign: 'center', padding: '40px' }}>
            Loading shipment queue…
          </div>
        ) : filteredOrders.length === 0 ? (
          <div className="order-card" style={{ textAlign: 'center', padding: '40px' }}>
            No shipments match the selected filter.
          </div>
        ) : (
          <div className="orders-grid">
            {filteredOrders.map((order, index) => {
              const result = results[order.order_id]
              const status = result?.result
              const ai = aiResults[order.order_id]

              const scoreClass =
                ai?.readiness_score >= 85
                  ? 'high'
                  : ai?.readiness_score >= 70
                  ? 'med'
                  : 'low'

              return (
                <article className="order-card" key={order.order_id}>
                  <div className="order-top">
                    <div className="order-seq">0{index + 1}</div>
                    <div className="order-meta">
                      <div className="order-meta-head">
                        <strong>{order.order_id}</strong>
                        <small>PayPal Txn: {order.transaction_id}</small>
                      </div>
                    </div>

                    <div className="status-badges">
                      {ai && !ai.loading && !ai.error && (
                        <span className={`score-chip ${scoreClass}`} title={ai.readiness_label}>
                          AI Score: {ai.readiness_score}/100
                        </span>
                      )}

                      <span
                        className={
                          'pill ' +
                          (status === 'PASS'
                            ? 'pill-pass'
                            : status === 'BLOCKED'
                            ? 'pill-blocked'
                            : status === 'WARNING'
                            ? 'pill-warn'
                            : 'pill-unchecked')
                        }
                      >
                        {result?.loading ? 'CHECKING…' : status || 'NOT CHECKED'}
                      </span>
                    </div>
                  </div>

                  {/* 5-Column Detail Breakdown */}
                  <div className="details-grid">
                    <div className="detail-col">
                      <small>Tracking Number</small>
                      <strong className={!order.tracking_number ? 'missing' : ''}>
                        {order.tracking_number || 'Missing Number'}
                      </strong>
                    </div>
                    <div className="detail-col">
                      <small>Carrier</small>
                      <strong>
                        {order.carrier === 'OTHER' ? order.carrier_name_other || 'OTHER' : order.carrier || 'Not provided'}
                      </strong>
                    </div>
                    <div className="detail-col">
                      <small>Shipment Status</small>
                      <strong>{order.status}</strong>
                    </div>
                    <div className="detail-col">
                      <small>Order Value</small>
                      <strong>
                        {order.amount ? `$${Number(order.amount).toFixed(2)} ${order.currency || 'USD'}` : '—'}
                      </strong>
                    </div>
                    <div className="detail-col">
                      <small>Destination Address</small>
                      <strong>{order.shipping_address || '—'}</strong>
                    </div>
                  </div>

                  {/* Evidence Snippet */}
                  {order.evidence_text && (
                    <div className="evidence-snippet">
                      <strong>Carrier Tracking Evidence Scan:</strong>
                      {order.evidence_text}
                    </div>
                  )}

                  {/* Findings */}
                  {result?.issues?.length > 0 && (
                    <div className="findings-box issues">
                      <strong>✕ Issues Requiring Resolution:</strong>
                      {result.issues.map((issue, i) => (
                        <p key={i}>• {issue.message}</p>
                      ))}
                    </div>
                  )}

                  {result?.warnings?.length > 0 && (
                    <div className="findings-box warnings">
                      <strong>! Review Recommended:</strong>
                      {result.warnings.map((warn, i) => (
                        <p key={i}>• {warn.message}</p>
                      ))}
                    </div>
                  )}

                  {status === 'PASS' && (
                    <div className="pass-callout">
                      ✓ Preliminary data-quality checks passed. Evidence ready for PayPal Seller Protection inspection.
                    </div>
                  )}

                  {/* Card Footer Actions */}
                  <div className="card-footer-row">
                    <span>
                      {status === 'PASS'
                        ? 'Data schema verified · Safe for preview'
                        : status === 'BLOCKED'
                        ? 'Resolve issues before proceeding'
                        : 'Pre-submission check'}
                    </span>
                    <div className="card-footer-actions">
                      <button
                        className="btn-secondary"
                        onClick={() => validate(order)}
                        disabled={result?.loading}
                      >
                        {result?.loading ? 'Checking…' : 'Validate →'}
                      </button>
                      <button
                        className="btn-secondary btn-ai"
                        onClick={() => openInspector(order)}
                      >
                        Inspect & Remediate ↗
                      </button>
                    </div>
                  </div>
                </article>
              )
            })}
          </div>
        )}

        {/* Footer */}
        <footer>
          <div>
            <strong>SHIPPROOF AI</strong> · Pre-Submission Shipment Evidence Control
          </div>
          <p>
            Deterministic checks and AI analysis assist in evidence quality; official dispute outcomes are determined by PayPal.
          </p>
        </footer>
      </main>

      {/* Drawer: AI Evidence Inspector & Interactive Remediation Sandbox */}
      {selectedOrder && (
        <div className="drawer-backdrop" onClick={() => setSelectedOrder(null)}>
          <div className="drawer-pane" onClick={e => e.stopPropagation()}>
            <div className="drawer-top">
              <div className="drawer-title-wrap">
                <h3>Evidence & Protection Inspector</h3>
                <small>
                  Order: <strong>{selectedOrder.order_id}</strong> · Transaction: {selectedOrder.transaction_id}
                </small>
              </div>
              <button
                className="btn-close"
                onClick={() => setSelectedOrder(null)}
                aria-label="Close"
              >
                ✕
              </button>
            </div>

            <div className="drawer-content">
              {inspectLoading || currentAiResult?.loading ? (
                <div style={{ textAlign: 'center', padding: '40px' }}>
                  Evaluating shipment evidence against PayPal Seller Protection criteria…
                </div>
              ) : currentAiResult?.error ? (
                <div className="findings-box issues">{currentAiResult.error}</div>
              ) : currentAiResult ? (
                <>
                  {/* Score Hero Meter */}
                  <div className="score-hero-box">
                    <div className="score-hero-info">
                      <div className="eyebrow" style={{ color: '#2b5220' }}>
                        PROTECTION READINESS RATING
                      </div>
                      <strong>{currentAiResult.readiness_label}</strong>
                      <p>
                        Auditable score based on carrier tracking integrity, $750+ signature compliance, and destination matching.
                      </p>
                    </div>
                    <div
                      className={
                        'score-meter ' +
                        (currentAiResult.readiness_score >= 85
                          ? 'high'
                          : currentAiResult.readiness_score >= 70
                          ? 'med'
                          : 'low')
                      }
                    >
                      {currentAiResult.readiness_score}
                    </div>
                  </div>

                  {currentValidation && currentValidation.result === 'BLOCKED' && (
                    <div className="findings-box issues" style={{ margin: 0 }}>
                      <strong>Data Quality Issues (Blocks PayPal Add Tracking Submission):</strong>
                      {currentValidation.issues?.map((iss, i) => (
                        <p key={i}>• {iss.message}</p>
                      ))}
                    </div>
                  )}

                  {/* PayPal Seller Protection Matrix */}
                  <div>
                    <div className="nav-section" style={{ color: 'var(--slate)', margin: '0 0 8px' }}>
                      PayPal Seller Protection Policy Matrix
                    </div>
                    <div className="matrix-container" style={{ gridTemplateColumns: 'repeat(2, minmax(0,1fr))' }}>
                      <div className="matrix-item">
                        <small>INR DEFENSE READINESS</small>
                        <span
                          className={
                            'matrix-status-tag ' +
                            (currentAiResult.seller_protection.item_not_received_eligible
                              ? 'pill-pass'
                              : 'pill-blocked')
                          }
                        >
                          {currentAiResult.seller_protection.item_not_received_eligible
                            ? 'DEFENSE SUPPORTED'
                            : 'EVIDENCE INCOMPLETE'}
                        </span>
                        <p>
                          {currentAiResult.seller_protection.item_not_received_eligible
                            ? 'Delivery record substantiates online proof of delivery to destination address.'
                            : 'Missing verifiable delivery status or $750+ signature proof.'}
                        </p>
                      </div>

                      <div className="matrix-item">
                        <small>UNAUTHORIZED TXN</small>
                        <span
                          className={
                            'matrix-status-tag ' +
                            (currentAiResult.seller_protection.unauthorized_transaction_eligible
                              ? 'pill-pass'
                              : 'pill-blocked')
                          }
                        >
                          {currentAiResult.seller_protection.unauthorized_transaction_eligible
                            ? 'DISPATCH PROVEN'
                            : 'INCOMPLETE PROOF'}
                        </span>
                        <p>Proof of shipment dispatch date and carrier tracking documentation.</p>
                      </div>

                      <div className="matrix-item">
                        <small>$750+ SIGNATURE</small>
                        <span
                          className={
                            'matrix-status-tag ' +
                            (currentAiResult.seller_protection.signature_confirmation.status === 'SATISFIED'
                              ? 'pill-pass'
                              : currentAiResult.seller_protection.signature_confirmation.status === 'NOT_REQUIRED'
                              ? 'pill-pass'
                              : currentAiResult.seller_protection.signature_confirmation.status === 'MERCHANT_ATTESTED_UNVERIFIED'
                              ? 'pill-warn'
                              : 'pill-blocked')
                          }
                        >
                          {currentAiResult.seller_protection.signature_confirmation.status === 'SATISFIED'
                            ? 'CARRIER VERIFIED'
                            : currentAiResult.seller_protection.signature_confirmation.status === 'MERCHANT_ATTESTED_UNVERIFIED'
                            ? 'ATTESTED (UNVERIFIED)'
                            : currentAiResult.seller_protection.signature_confirmation.status === 'NOT_REQUIRED'
                            ? 'NOT REQUIRED'
                            : 'MISSING REQUIRED'}
                        </span>
                        <p>
                          {currentAiResult.seller_protection.signature_confirmation.required
                            ? currentAiResult.seller_protection.signature_confirmation.status === 'SATISFIED'
                              ? 'Carrier delivery log documents verified recipient signature.'
                              : currentAiResult.seller_protection.signature_confirmation.status === 'MERCHANT_ATTESTED_UNVERIFIED'
                              ? 'Merchant noted signature on file, but carrier tracking has not confirmed it independently.'
                              : 'Mandatory for transactions >= $750.00 USD under PayPal Seller Protection policy.'
                            : 'Standard value (< $750); signature confirmation optional.'}
                        </p>
                      </div>

                      <div className="matrix-item">
                        <small>POLICY DATE APPLICABILITY</small>
                        <span
                          className={
                            'matrix-status-tag ' +
                            (currentAiResult.seller_protection.signature_confirmation.policy_applicability === 'CONFIRMED'
                              ? 'pill-pass'
                              : currentAiResult.seller_protection.signature_confirmation.policy_applicability === 'PRE_POLICY'
                              ? 'pill-unchecked'
                              : 'pill-warn')
                          }
                        >
                          {currentAiResult.seller_protection.signature_confirmation.policy_applicability === 'CONFIRMED'
                            ? 'POLICY APPLIES'
                            : currentAiResult.seller_protection.signature_confirmation.policy_applicability === 'PRE_POLICY'
                            ? 'PRE-POLICY DATE'
                            : 'DATE MISSING'}
                        </span>
                        <p>
                          {currentAiResult.seller_protection.signature_confirmation.policy_applicability === 'CONFIRMED'
                            ? `PayPal $750+ signature policy (eff. ${currentAiResult.seller_protection.signature_confirmation.policy_effective_date}) applies to this transaction.`
                            : currentAiResult.seller_protection.signature_confirmation.policy_applicability === 'PRE_POLICY'
                            ? `Transaction predates the $750+ policy (eff. ${currentAiResult.seller_protection.signature_confirmation.policy_effective_date}). Manual review recommended.`
                            : 'Transaction processing date unavailable. Policy applicability requires manual review — provide transaction_date to confirm.'}
                        </p>
                      </div>
                    </div>
                    <p style={{ fontSize: '11px', color: 'var(--text-muted)', fontStyle: 'italic', marginTop: '8px' }}>
                      * Evidence quality assessment only. Official Seller Protection eligibility is adjudicated exclusively by PayPal during dispute review.
                    </p>
                  </div>

                  {/* Interactive Remediation Sandbox */}
                  <div className="remediation-box">
                    <h4>Interactive Evidence Remediation Sandbox</h4>
                    <p>
                      Update carrier delivery notes, tracking numbers, or order details to test real-time recalculation of your protection readiness:
                    </p>

                    <div className="interactive-form-grid">
                      <div className="form-group">
                        <label>Tracking Number</label>
                        <input
                          type="text"
                          className="form-control"
                          value={remediationForm.tracking_number}
                          onChange={e => setRemediationForm({ ...remediationForm, tracking_number: e.target.value })}
                          placeholder="e.g. 781234567890"
                        />
                      </div>

                      <div className="form-group">
                        <label>Carrier</label>
                        <select
                          className="form-control"
                          value={remediationForm.carrier}
                          onChange={e => setRemediationForm({ ...remediationForm, carrier: e.target.value })}
                        >
                          <option value="FEDEX">FEDEX</option>
                          <option value="UPS">UPS</option>
                          <option value="USPS">USPS</option>
                          <option value="DHL">DHL</option>
                          <option value="OTHER">OTHER</option>
                        </select>
                      </div>

                      {remediationForm.carrier === 'OTHER' && (
                        <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                          <label>Custom Carrier Name (Required by PayPal for OTHER)</label>
                          <input
                            type="text"
                            className="form-control"
                            value={remediationForm.carrier_name_other || ''}
                            onChange={e => setRemediationForm({ ...remediationForm, carrier_name_other: e.target.value })}
                            placeholder="e.g. OnTrac, LaserShip, Royal Mail"
                          />
                        </div>
                      )}

                      <div className="form-group">
                        <label>Order Amount ($ USD)</label>
                        <input
                          type="number"
                          className="form-control"
                          value={remediationForm.amount}
                          onChange={e => setRemediationForm({ ...remediationForm, amount: e.target.value })}
                          placeholder="e.g. 980.00"
                        />
                      </div>

                      <div className="form-checkbox-row">
                        <input
                          type="checkbox"
                          id="sig_check"
                          checked={remediationForm.signature_obtained}
                          onChange={e => setRemediationForm({ ...remediationForm, signature_obtained: e.target.checked })}
                        />
                        <label htmlFor="sig_check" style={{ cursor: 'pointer', margin: 0 }}>
                          <span>Merchant Attestation: Physical/ePOD Signature Slip On File</span>
                          <small style={{ display: 'block', fontSize: '10px', color: '#687e6d', fontWeight: 400, marginTop: '2px' }}>
                            Note: PayPal requires online verifiable carrier delivery documentation for $750+ INR protection. Merchant attestation alone without carrier scan corroboration is marked unverified.
                          </small>
                        </label>
                      </div>
                    </div>

                    <div className="form-group" style={{ marginTop: '12px' }}>
                      <label>Official Carrier Scan Evidence Notes / ePOD Record</label>
                      <textarea
                        className="form-control"
                        rows="3"
                        value={remediationForm.evidence_text}
                        onChange={e => setRemediationForm({ ...remediationForm, evidence_text: e.target.value })}
                        placeholder="e.g. Delivered and signed by: C. Adams, Boston, MA 02108. FedEx Direct Signature confirmation on file."
                      />
                      <small style={{ display: 'block', fontSize: '10px', color: '#687e6d', marginTop: '4px' }}>
                        Carrier scan text must document recipient signature confirmation and delivery location to satisfy Seller Protection criteria for high-value orders ($750+).
                      </small>
                    </div>

                    <div className="remediation-actions">
                      <button
                        className="btn-primary"
                        onClick={handleRemediationSubmit}
                        disabled={inspectLoading}
                      >
                        {inspectLoading ? 'Recalculating…' : 'Recalculate Protection Score ↻'}
                      </button>
                    </div>
                  </div>

                  {/* AI Strengths & Risk Insights */}
                  <div>
                    <div className="nav-section" style={{ color: '#314738', margin: '0 0 8px' }}>
                      Audit Findings & Recommendations
                    </div>
                    <div className="insights-wrap">
                      {currentAiResult.strengths?.map((item, idx) => (
                        <div className="insight-row strength" key={`s-${idx}`}>
                          <span className="insight-icon">
                            <CheckIcon />
                          </span>
                          <span>{item}</span>
                        </div>
                      ))}
                      {currentAiResult.risk_factors?.map((item, idx) => (
                        <div className="insight-row risk" key={`r-${idx}`}>
                          <span className="insight-icon">
                            <AlertIcon />
                          </span>
                          <span>{item}</span>
                        </div>
                      ))}
                      {currentAiResult.recommendations?.map((item, idx) => (
                        <div className="insight-row recom" key={`rec-${idx}`}>
                          <span className="insight-icon">
                            <ArrowIcon />
                          </span>
                          <span>{item}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Formatted PayPal Add Tracking API Payload Preview */}
                  <div className="code-preview-card">
                    <div className="code-header">
                      <span>PAYPAL SANDBOX ADD TRACKING PREVIEW (POST /v1/shipping/trackers-batch)</span>
                      <button
                        className="btn-secondary"
                        style={{ padding: '4px 8px', fontSize: '10px' }}
                        onClick={() => copyPayload(currentAiResult.paypal_payload_preview?.trackers)}
                      >
                        {copiedPayload ? 'Copied ✓' : 'Copy JSON'}
                      </button>
                    </div>

                    <pre className="code-pre">
                      {JSON.stringify(currentAiResult.paypal_payload_preview?.trackers, null, 2)}
                    </pre>

                    <div className="safety-gate-notice">
                      <span style={{ display: 'grid', placeItems: 'center' }}>
                        <LockIcon />
                      </span>
                      <span>
                        <strong>Safety Gate Active:</strong> Submissions are locked locally (<code>PAYPAL_TRACKING_SUBMISSION_ENABLED=false</code>). No tracking records will be sent to PayPal.
                      </span>
                    </div>
                  </div>
                </>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

createRoot(document.getElementById('root')).render(<App />)
