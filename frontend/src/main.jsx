import React, { useEffect, useState, useMemo } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

// ─── ShipProof AI — unified shell across all routes ───────────────────────────
// Routes:
//   /                    Shipment Evidence Review Dashboard
//   /manifests           Shipment Management & Product Manifests
//   /packing             Packing Station & Gemini Inspection
//   /inspections         AI Inspection Results & Human Review
//   /checkout            PayPal Sandbox Buyer Checkout
//   /checkout/return     PayPal Payment Return / Capture
//   /checkout/cancel     PayPal Payment Cancellation

// ─── Shared Icons ─────────────────────────────────────────────────────────────
const CheckIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ flexShrink: 0 }}>
    <polyline points="20 6 9 17 4 12" />
  </svg>
)

const AlertIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ flexShrink: 0 }}>
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
)

const ArrowIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ flexShrink: 0 }}>
    <line x1="5" y1="12" x2="19" y2="12" />
    <polyline points="12 5 19 12 12 19" />
  </svg>
)

const LockIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ flexShrink: 0 }}>
    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
  </svg>
)

const SearchIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="11" cy="11" r="8" />
    <line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
)

const ShieldIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
  </svg>
)

const CartIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="9" cy="21" r="1" /><circle cx="20" cy="21" r="1" />
    <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" />
  </svg>
)

const PayPalIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M7.5 21H3L6.75 3h6.75c2.25 0 4.5 1.5 4.5 4.5 0 4.5-3.75 6-6.75 6H9L7.5 21zm3-10.5h1.5c1.5 0 2.25-.75 2.25-2.25S13.5 6 12 6H10.5l-1.125 5.25L10.5 10.5z" opacity=".6" />
    <path d="M11.25 21H6.75L10.5 6h6.75c2.25 0 4.5 1.5 4.5 4.5 0 4.5-3.75 6-6.75 6h-2.25L11.25 21zm3-10.5h1.5c1.5 0 2.25-.75 2.25-2.25S16.5 6 15 6h-1.5L12.375 10.5l2.625.001-.75-.001z" />
  </svg>
)

const SuccessCircleIcon = () => (
  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
    <polyline points="22 4 12 14.01 9 11.01" />
  </svg>
)

const CancelCircleIcon = () => (
  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="10" />
    <line x1="15" y1="9" x2="9" y2="15" />
    <line x1="9" y1="9" x2="15" y2="15" />
  </svg>
)

const SpinnerIcon = () => (
  <svg className="spinner-icon" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
    <path d="M12 2a10 10 0 0 1 10 10" />
  </svg>
)

const ManifestIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
    <line x1="16" y1="13" x2="8" y2="13" />
    <line x1="16" y1="17" x2="8" y2="17" />
    <polyline points="10 9 9 9 8 9" />
  </svg>
)

const CameraIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
    <circle cx="12" cy="13" r="4" />
  </svg>
)

const EyeIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
)

// ─── Shared Sidebar Component ─────────────────────────────────────────────────
function Sidebar({ currentPath, ordersCount, navigateTo }) {
  const isReview = currentPath === '/'
  const isManifests = currentPath === '/manifests'
  const isPacking = currentPath === '/packing'
  const isInspections = currentPath === '/inspections'
  const isCheckout = currentPath === '/checkout' || currentPath === '/checkout/return' || currentPath === '/checkout/cancel'

  return (
    <aside className="sidebar" aria-label="Application navigation">
      <div className="brand">
        <div className="brand-icon" aria-hidden="true">S</div>
        <div className="brand-title">
          <strong>ShipProof AI</strong>
          <small>PAYPAL EVIDENCE CONTROL</small>
        </div>
      </div>

      <nav aria-label="Main navigation">
        <div className="nav-section">Evidence Workflows</div>
        <button
          className={`nav-item nav-item-btn ${isReview ? 'active' : ''}`}
          onClick={() => navigateTo('/')}
          aria-current={isReview ? 'page' : undefined}
        >
          <span aria-hidden="true">▦</span>
          <span>Shipment Review</span>
          <span className="nav-badge" aria-label={`${ordersCount} shipments`}>{ordersCount}</span>
        </button>
        <button
          className={`nav-item nav-item-btn ${isManifests ? 'active' : ''}`}
          onClick={() => navigateTo('/manifests')}
          aria-current={isManifests ? 'page' : undefined}
        >
          <span aria-hidden="true"><ManifestIcon /></span>
          <span>Manifests</span>
        </button>
        <button
          className={`nav-item nav-item-btn ${isPacking ? 'active' : ''}`}
          onClick={() => navigateTo('/packing')}
          aria-current={isPacking ? 'page' : undefined}
        >
          <span aria-hidden="true"><CameraIcon /></span>
          <span>Packing Station</span>
        </button>
        <button
          className={`nav-item nav-item-btn ${isInspections ? 'active' : ''}`}
          onClick={() => navigateTo('/inspections')}
          aria-current={isInspections ? 'page' : undefined}
        >
          <span aria-hidden="true"><EyeIcon /></span>
          <span>AI Inspections</span>
        </button>

        <div className="nav-section" style={{ marginTop: '16px' }}>Store &amp; Checkout</div>
        <button
          className={`nav-item nav-item-btn ${isCheckout ? 'active' : ''}`}
          onClick={() => navigateTo('/checkout')}
          aria-current={isCheckout ? 'page' : undefined}
        >
          <span aria-hidden="true"><CartIcon /></span>
          <span>New Checkout</span>
        </button>
      </nav>

      <div className="side-card">
        <div className="side-card-header">
          <span className="pulse" aria-hidden="true"></span>
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
  )
}

// ─── Main App Component ───────────────────────────────────────────────────────
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

  // UI state for Dashboard
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

  // Checkout state
  const [catalog, setCatalog] = useState([])
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [catalogError, setCatalogError] = useState('')
  const [cart, setCart] = useState({})
  const [checkoutDetails, setCheckoutDetails] = useState({
    buyerName: '',
    addressLine1: '',
    addressLine2: '',
    city: '',
    state: '',
    postalCode: '',
    countryCode: 'IN'
  })
  const [checkoutLoading, setCheckoutLoading] = useState(false)
  const [checkoutError, setCheckoutError] = useState('')
  const [captureLoading, setCaptureLoading] = useState(false)
  const [captureResult, setCaptureResult] = useState(null)
  const [captureError, setCaptureError] = useState('')
  const [currentPath, setCurrentPath] = useState(window.location.pathname)

  // Shared active shipment context across workflows
  const [activeShipmentId, setActiveShipmentId] = useState(null)

  // Mount-only effect: register popstate listener & fetch initial shipments / paypal status
  useEffect(() => {
    const handleRouteChange = () => setCurrentPath(window.location.pathname)
    window.addEventListener('popstate', handleRouteChange)

    fetch(`${API_BASE}/api/orders`)
      .then(r => {
        if (!r.ok) throw new Error('Could not load shipments')
        return r.json()
      })
      .then(data => {
        const ords = data.orders || []
        setOrders(ords)
        if (ords.length > 0 && !activeShipmentId) {
          setActiveShipmentId(ords[0].order_id)
        }
      })
      .catch(() => setError('Cannot connect to the backend. Make sure it is running.'))
      .finally(() => setLoading(false))

    fetch(`${API_BASE}/api/paypal/status`)
      .then(r => {
        if (!r.ok) throw new Error('Could not load PayPal status')
        return r.json()
      })
      .then(data => setPaypal(data))
      .catch(() => setPaypal({ error: 'PayPal status unavailable' }))

    return () => window.removeEventListener('popstate', handleRouteChange)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Route-specific side effects
  useEffect(() => {
    if (currentPath === '/checkout') {
      loadCatalog()
    }
    if (currentPath === '/checkout/return') {
      handleCaptureReturn()
    }
  }, [currentPath]) // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Shipment Review functions ────────────────────────────────────────────
  async function validate(order) {
    setResults(old => ({ ...old, [order.order_id]: { loading: true } }))
    try {
      const response = await fetch(`${API_BASE}/api/validate`, {
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

  async function analyzeOrderEvidence(order) {
    setAiResults(old => ({ ...old, [order.order_id]: { loading: true } }))
    try {
      const response = await fetch(`${API_BASE}/api/analyze-evidence`, {
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

  async function testPayPalConnection() {
    setOauthTesting(true)
    try {
      const res = await fetch(`${API_BASE}/api/paypal/verify-connection`, { method: 'POST' })
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

    if (!aiResults[order.order_id]) {
      setInspectLoading(true)
      analyzeOrderEvidence(order).finally(() => setInspectLoading(false))
    }
    if (!results[order.order_id]) {
      validate(order)
    }
  }

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

    setOrders(prev => prev.map(o => o.order_id === updatedOrder.order_id ? updatedOrder : o))
    setSelectedOrder(updatedOrder)

    await Promise.all([
      validate(updatedOrder),
      analyzeOrderEvidence(updatedOrder)
    ])

    setInspectLoading(false)
  }

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

  // ─── Checkout functions ───────────────────────────────────────────────────
  async function loadCatalog() {
    setCatalogLoading(true)
    setCatalogError('')
    try {
      const res = await fetch(`${API_BASE}/api/catalog`)
      if (!res.ok) throw new Error('Could not load product catalog')
      const data = await res.json()
      setCatalog(data.products || [])
    } catch {
      setCatalogError('Could not load product catalog. Make sure the backend is running.')
    } finally {
      setCatalogLoading(false)
    }
  }

  function addToCart(sku) {
    setCart(prev => ({ ...prev, [sku]: (prev[sku] || 0) + 1 }))
  }

  function removeFromCart(sku) {
    setCart(prev => {
      const next = { ...prev }
      if (next[sku] > 1) next[sku] -= 1
      else delete next[sku]
      return next
    })
  }

  function getCartItems() {
    return Object.entries(cart).map(([sku, quantity]) => ({ sku, quantity }))
  }

  function getCartTotal() {
    return getCartItems().reduce((sum, { sku, quantity }) => {
      const product = catalog.find(p => p.sku === sku)
      return sum + (product ? parseFloat(product.price) * quantity : 0)
    }, 0)
  }

  async function handleCheckout() {
    const items = getCartItems()
    if (items.length === 0) {
      setCheckoutError('Please add at least one item to your cart.')
      return
    }

    const buyerName = checkoutDetails.buyerName.trim()
    const addressLine1 = checkoutDetails.addressLine1.trim()
    const city = checkoutDetails.city.trim()
    const postalCode = checkoutDetails.postalCode.trim()
    const countryCode = checkoutDetails.countryCode.trim().toUpperCase()
    const regionRequiredCountries = ['AR', 'BR', 'CA', 'CN', 'ID', 'IN', 'JP', 'MX', 'TH', 'US']
    const regionRequired = regionRequiredCountries.includes(countryCode)
    if (
      !buyerName ||
      !addressLine1 ||
      !city ||
      !postalCode ||
      !/^[A-Z]{2}$/.test(countryCode) ||
      (regionRequired && !checkoutDetails.state.trim())
    ) {
      setCheckoutError('Enter the recipient name and all required delivery address fields, including state or region where required.')
      return
    }

    setCheckoutLoading(true)
    setCheckoutError('')
    try {
      const res = await fetch(`${API_BASE}/api/checkout/orders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          items,
          currency: 'USD',
          buyer_name: buyerName,
          shipping_address: {
            address_line_1: addressLine1,
            address_line_2: checkoutDetails.addressLine2.trim(),
            city,
            state: checkoutDetails.state.trim(),
            postal_code: postalCode,
            country_code: countryCode
          }
        })
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail) || 'Checkout failed')
      }
      const data = await res.json()

      sessionStorage.setItem('shipproof_order_id', data.order_id)
      sessionStorage.setItem('shipproof_paypal_order_id', data.paypal_order_id)

      if (data.approval_url) {
        window.location.href = data.approval_url
      } else {
        setCheckoutError('PayPal did not provide an approval URL.')
      }
    } catch (err) {
      setCheckoutError(err.message || 'Checkout failed. Check the backend.')
    } finally {
      setCheckoutLoading(false)
    }
  }

  async function handleCaptureReturn() {
    const orderId = sessionStorage.getItem('shipproof_order_id')
    if (!orderId) {
      setCaptureError('No order found in session. Please start a new checkout.')
      return
    }

    setCaptureLoading(true)
    setCaptureError('')
    try {
      const res = await fetch(`${API_BASE}/api/checkout/orders/${orderId}/capture`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail) || 'Payment capture failed')
      }
      const data = await res.json()
      if (data.payment_status === 'PAID' || data.already_captured) {
        sessionStorage.removeItem('shipproof_order_id')
        sessionStorage.removeItem('shipproof_paypal_order_id')
      }
      setCaptureResult(data)

      // Refresh orders list so the new shipment is immediately available
      fetch(`${API_BASE}/api/orders`)
        .then(r => r.ok ? r.json() : null)
        .then(fresh => {
          if (fresh?.orders) {
            setOrders(fresh.orders)
            if (data.shipment_order_id) {
              setActiveShipmentId(data.shipment_order_id)
            }
          }
        })
        .catch(() => {})
    } catch (err) {
      setCaptureError(err.message || 'Payment capture failed. Check the backend.')
    } finally {
      setCaptureLoading(false)
    }
  }

  function navigateTo(path, opts = {}) {
    window.history.pushState({}, '', path)
    if (path === '/checkout') {
      setCart({})
      setCheckoutError('')
      setCatalogError('')
    }
    if (path === '/') {
      setCheckoutError('')
    }
    if (path === '/checkout/return') {
      setCaptureError('')
      setCaptureResult(null)
    }
    if (path === '/checkout/cancel') {
      setCaptureError('')
      setCaptureResult(null)
    }
    if (opts.shipmentId) {
      setActiveShipmentId(opts.shipmentId)
    }
    setCurrentPath(path)
  }

  // ─── Route views ──────────────────────────────────────────────────────────
  const isDashboard = currentPath === '/'

  return (
    <div className="app-shell">
      <Sidebar
        currentPath={currentPath}
        ordersCount={orders.length}
        navigateTo={navigateTo}
      />

      {/* Main workspace routing */}
      {currentPath === '/checkout' && (
        <CheckoutCatalogView
          catalog={catalog}
          catalogLoading={catalogLoading}
          catalogError={catalogError}
          cart={cart}
          checkoutLoading={checkoutLoading}
          checkoutError={checkoutError}
          checkoutDetails={checkoutDetails}
          setCheckoutDetails={setCheckoutDetails}
          loadCatalog={loadCatalog}
          addToCart={addToCart}
          removeFromCart={removeFromCart}
          getCartItems={getCartItems}
          getCartTotal={getCartTotal}
          handleCheckout={handleCheckout}
          navigateTo={navigateTo}
        />
      )}

      {currentPath === '/checkout/return' && (
        <CheckoutReturnView
          captureLoading={captureLoading}
          captureError={captureError}
          captureResult={captureResult}
          navigateTo={navigateTo}
        />
      )}

      {currentPath === '/checkout/cancel' && (
        <CheckoutCancelView navigateTo={navigateTo} />
      )}

      {currentPath === '/manifests' && (
        <ShipmentsManifestView
          orders={orders}
          activeShipmentId={activeShipmentId}
          setActiveShipmentId={setActiveShipmentId}
          navigateTo={navigateTo}
        />
      )}

      {currentPath === '/packing' && (
        <PackingStationView
          orders={orders}
          activeShipmentId={activeShipmentId}
          setActiveShipmentId={setActiveShipmentId}
          navigateTo={navigateTo}
        />
      )}

      {currentPath === '/inspections' && (
        <InspectionsReviewView
          orders={orders}
          setOrders={setOrders}
          activeShipmentId={activeShipmentId}
          setActiveShipmentId={setActiveShipmentId}
          navigateTo={navigateTo}
        />
      )}

      {isDashboard && (
        <ShipmentReviewMain
          orders={orders}
          filteredOrders={filteredOrders}
          results={results}
          aiResults={aiResults}
          loading={loading}
          error={error}
          paypal={paypal}
          oauthTesting={oauthTesting}
          oauthVerified={oauthVerified}
          oauthMessage={oauthMessage}
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          showArchDetails={showArchDetails}
          setShowArchDetails={setShowArchDetails}
          batchAiLoading={batchAiLoading}
          batchValidateLoading={batchValidateLoading}
          readyChecksCount={readyChecksCount}
          blockedCount={blockedCount}
          protectionReadyCount={protectionReadyCount}
          testPayPalConnection={testPayPalConnection}
          handleAnalyzeAll={handleAnalyzeAll}
          handleValidateAll={handleValidateAll}
          validate={validate}
          openInspector={openInspector}
          navigateTo={navigateTo}
        />
      )}

      {/* Drawer: AI Evidence Inspector — only on dashboard */}
      {selectedOrder && isDashboard && (
        <div
          className="drawer-backdrop"
          onClick={() => setSelectedOrder(null)}
          role="dialog"
          aria-modal="true"
          aria-label="Evidence and Protection Inspector"
        >
          <div className="drawer-pane" onClick={e => e.stopPropagation()}>
            <div className="drawer-top">
              <div className="drawer-title-wrap">
                <h3>Evidence &amp; Protection Inspector</h3>
                <small>
                  Order: <strong>{selectedOrder.order_id}</strong> · Transaction: {selectedOrder.transaction_id}
                </small>
              </div>
              <button
                className="btn-close"
                onClick={() => setSelectedOrder(null)}
                aria-label="Close inspector"
              >
                ✕
              </button>
            </div>

            <div className="drawer-content">
              {inspectLoading || currentAiResult?.loading ? (
                <div style={{ textAlign: 'center', padding: '40px' }} role="status" aria-live="polite">
                  Evaluating shipment evidence against PayPal Seller Protection criteria…
                </div>
              ) : currentAiResult?.error ? (
                <div className="findings-box issues" role="alert">{currentAiResult.error}</div>
              ) : currentAiResult ? (
                <>
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
                        (currentAiResult.readiness_score >= 85 ? 'high' : currentAiResult.readiness_score >= 70 ? 'med' : 'low')
                      }
                      aria-label={`Readiness score: ${currentAiResult.readiness_score} out of 100`}
                    >
                      {currentAiResult.readiness_score}
                    </div>
                  </div>

                  {currentValidation && currentValidation.result === 'BLOCKED' && (
                    <div className="findings-box issues" style={{ margin: 0 }} role="alert">
                      <strong>Data Quality Issues (Blocks PayPal Add Tracking Submission):</strong>
                      {currentValidation.issues?.map((iss, i) => (
                        <p key={i}>• {iss.message}</p>
                      ))}
                    </div>
                  )}

                  <div>
                    <div className="nav-section" style={{ color: 'var(--slate)', margin: '0 0 8px' }}>
                      PayPal Seller Protection Policy Matrix
                    </div>
                    <div className="matrix-container" style={{ gridTemplateColumns: 'repeat(2, minmax(0,1fr))' }}>
                      <div className="matrix-item">
                        <small>INR DEFENSE READINESS</small>
                        <span className={'matrix-status-tag ' + (currentAiResult.seller_protection.item_not_received_eligible ? 'pill-pass' : 'pill-blocked')}>
                          {currentAiResult.seller_protection.item_not_received_eligible ? 'DEFENSE SUPPORTED' : 'EVIDENCE INCOMPLETE'}
                        </span>
                        <p>
                          {currentAiResult.seller_protection.item_not_received_eligible
                            ? 'Delivery record substantiates online proof of delivery to destination address.'
                            : 'Missing verifiable delivery status or $750+ signature proof.'}
                        </p>
                      </div>

                      <div className="matrix-item">
                        <small>UNAUTHORIZED TXN</small>
                        <span className={'matrix-status-tag ' + (currentAiResult.seller_protection.unauthorized_transaction_eligible ? 'pill-pass' : 'pill-blocked')}>
                          {currentAiResult.seller_protection.unauthorized_transaction_eligible ? 'DISPATCH PROVEN' : 'INCOMPLETE PROOF'}
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

                  <div className="remediation-box">
                    <h4>Interactive Evidence Remediation Sandbox</h4>
                    <p>
                      Update carrier delivery notes, tracking numbers, or order details to test real-time recalculation of your protection readiness:
                    </p>

                    <div className="interactive-form-grid">
                      <div className="form-group">
                        <label htmlFor="rem-tracking">Tracking Number</label>
                        <input
                          id="rem-tracking"
                          type="text"
                          className="form-control"
                          value={remediationForm.tracking_number}
                          onChange={e => setRemediationForm({ ...remediationForm, tracking_number: e.target.value })}
                          placeholder="e.g. 781234567890"
                        />
                      </div>

                      <div className="form-group">
                        <label htmlFor="rem-carrier">Carrier</label>
                        <select
                          id="rem-carrier"
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
                          <label htmlFor="rem-carrier-name">Custom Carrier Name (Required by PayPal for OTHER)</label>
                          <input
                            id="rem-carrier-name"
                            type="text"
                            className="form-control"
                            value={remediationForm.carrier_name_other || ''}
                            onChange={e => setRemediationForm({ ...remediationForm, carrier_name_other: e.target.value })}
                            placeholder="e.g. OnTrac, LaserShip, Royal Mail"
                          />
                        </div>
                      )}

                      <div className="form-group">
                        <label htmlFor="rem-amount">Order Amount ($ USD)</label>
                        <input
                          id="rem-amount"
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
                      <label htmlFor="rem-evidence">Official Carrier Scan Evidence Notes / ePOD Record</label>
                      <textarea
                        id="rem-evidence"
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

                  <div>
                    <div className="nav-section" style={{ color: '#314738', margin: '0 0 8px' }}>
                      Audit Findings &amp; Recommendations
                    </div>
                    <div className="insights-wrap">
                      {currentAiResult.strengths?.map((item, idx) => (
                        <div className="insight-row strength" key={`s-${idx}`}>
                          <span className="insight-icon"><CheckIcon /></span>
                          <span>{item}</span>
                        </div>
                      ))}
                      {currentAiResult.risk_factors?.map((item, idx) => (
                        <div className="insight-row risk" key={`r-${idx}`}>
                          <span className="insight-icon"><AlertIcon /></span>
                          <span>{item}</span>
                        </div>
                      ))}
                      {currentAiResult.recommendations?.map((item, idx) => (
                        <div className="insight-row recom" key={`rec-${idx}`}>
                          <span className="insight-icon"><ArrowIcon /></span>
                          <span>{item}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="code-preview-card">
                    <div className="code-header">
                      <span>PAYPAL SANDBOX ADD TRACKING PREVIEW (POST /v1/shipping/trackers-batch)</span>
                      <button
                        className="btn-secondary"
                        style={{ padding: '4px 8px', fontSize: '10px' }}
                        onClick={() => copyPayload(currentAiResult.paypal_payload_preview?.trackers)}
                        aria-label={copiedPayload ? 'Copied to clipboard' : 'Copy JSON payload to clipboard'}
                      >
                        {copiedPayload ? 'Copied ✓' : 'Copy JSON'}
                      </button>
                    </div>
                    <pre className="code-pre">
                      {JSON.stringify(currentAiResult.paypal_payload_preview?.trackers, null, 2)}
                    </pre>
                    <div className="safety-gate-notice">
                      <span style={{ display: 'grid', placeItems: 'center' }}><LockIcon /></span>
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

// ─── Shipment Review Main Component ───────────────────────────────────────────
function ShipmentReviewMain({
  orders,
  filteredOrders,
  results,
  aiResults,
  loading,
  error,
  paypal,
  oauthTesting,
  oauthVerified,
  oauthMessage,
  activeTab,
  setActiveTab,
  searchQuery,
  setSearchQuery,
  showArchDetails,
  setShowArchDetails,
  batchAiLoading,
  batchValidateLoading,
  readyChecksCount,
  blockedCount,
  protectionReadyCount,
  testPayPalConnection,
  handleAnalyzeAll,
  handleValidateAll,
  validate,
  openInspector,
  navigateTo
}) {
  return (
    <main className="main" id="main-content">
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
            <span className={`pulse ${oauthVerified ? '' : 'warn'}`} aria-hidden="true"></span>
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

      <section className="hero" aria-label="ShipProof AI overview">
        <div className="hero-copy">
          <div className="eyebrow">
            <span aria-hidden="true">●</span> PRE-SUBMISSION SHIPMENT EVIDENCE &amp; SELLER PROTECTION
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

        <div className="hero-art-card" aria-hidden="true">
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

      <section className="architecture-banner">
        <div className="arch-info">
          <div className="arch-badge">AUDITABLE ENGINE</div>
          <div className="arch-text">
            <strong>Deterministic NLP &amp; PayPal Policy Rules Engine</strong>
            <p>
              Zero-hallucination compliance architecture: evaluates carrier tracking regexes, milestone timelines, destination matching, and PayPal's $750+ signature threshold.
            </p>
          </div>
        </div>
        <button
          className="arch-criteria-toggle"
          onClick={() => setShowArchDetails(prev => !prev)}
          aria-expanded={showArchDetails}
        >
          {showArchDetails ? 'Hide criteria ▲' : 'View 5 core criteria ▼'}
        </button>
      </section>

      {showArchDetails && (
        <div className="arch-details-drawer">
          <strong>Evaluated Seller Protection &amp; Data Quality Checks:</strong>
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

      <section className="stats-grid" aria-label="Operational metrics">
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

      {error && (
        <div className="findings-box issues" role="alert" style={{ marginBottom: '20px' }}>
          {error}
        </div>
      )}

      <div className="filter-bar" role="toolbar" aria-label="Filter shipments">
        <div className="filter-tabs" role="tablist">
          <button
            role="tab"
            aria-selected={activeTab === 'all'}
            className={`filter-tab ${activeTab === 'all' ? 'active' : ''}`}
            onClick={() => setActiveTab('all')}
          >
            All Shipments <span>{orders.length}</span>
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'needs-remediation'}
            className={`filter-tab ${activeTab === 'needs-remediation' ? 'active' : ''}`}
            onClick={() => setActiveTab('needs-remediation')}
          >
            Needs Remediation <span>{blockedCount}</span>
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'protection-ready'}
            className={`filter-tab ${activeTab === 'protection-ready' ? 'active' : ''}`}
            onClick={() => setActiveTab('protection-ready')}
          >
            Protection Ready <span>{protectionReadyCount}</span>
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'delivered'}
            className={`filter-tab ${activeTab === 'delivered' ? 'active' : ''}`}
            onClick={() => setActiveTab('delivered')}
          >
            Delivered <span>{orders.filter(o => o.status === 'DELIVERED').length}</span>
          </button>
        </div>
        <div className="search-input-wrap">
          <span className="search-icon" aria-hidden="true">
            <SearchIcon />
          </span>
          <input
            type="search"
            className="search-input"
            placeholder="Search by order, txn, carrier…"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            aria-label="Search shipments"
          />
        </div>
      </div>

      {loading ? (
        <div className="order-card" style={{ textAlign: 'center', padding: '40px' }} role="status" aria-live="polite">
          Loading shipment queue…
        </div>
      ) : filteredOrders.length === 0 ? (
        <div className="order-card" style={{ textAlign: 'center', padding: '40px' }} role="status">
          No shipments match the selected filter.
        </div>
      ) : (
        <div className="orders-grid">
          {filteredOrders.map((order, index) => {
            const result = results[order.order_id]
            const status = result?.result
            const ai = aiResults[order.order_id]
            const scoreClass = ai?.readiness_score >= 85 ? 'high' : ai?.readiness_score >= 70 ? 'med' : 'low'

            return (
              <article className="order-card" key={order.order_id}>
                <div className="order-top">
                  <div className="order-seq" aria-hidden="true">0{index + 1}</div>
                  <div className="order-meta">
                    <div className="order-meta-head">
                      <strong>{order.order_id}</strong>
                      {order.checkout_order_id && (
                        <span className="pill pill-pass" style={{ fontSize: '10px', padding: '2px 6px', marginLeft: '6px' }}>
                          PAID CHECKOUT
                        </span>
                      )}
                      <small>PayPal Txn: {order.transaction_id || order.paypal_capture_id || '—'}</small>
                      {order.checkout_order_id && (
                        <small style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                          Order: {order.checkout_order_id.slice(0, 8)}… · Capture: {order.paypal_capture_id || '—'}
                        </small>
                      )}
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
                    <small>Recipient</small>
                    <strong>{order.buyer_name || '—'}</strong>
                  </div>
                  <div className="detail-col">
                    <small>Destination Address</small>
                    <strong>{order.shipping_address || '—'}</strong>
                  </div>
                </div>

                {order.evidence_text && (
                  <div className="evidence-snippet">
                    <strong>Carrier Tracking Evidence Scan:</strong>
                    {order.evidence_text}
                  </div>
                )}

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
                      onClick={() => navigateTo('/manifests', { shipmentId: order.order_id })}
                    >
                      Manifest ↗
                    </button>
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
                      Inspect &amp; Remediate ↗
                    </button>
                  </div>
                </div>
              </article>
            )
          })}
        </div>
      )}

      <footer>
        <div>
          <strong>SHIPPROOF AI</strong> · Pre-Submission Shipment Evidence Control
        </div>
        <p>
          Deterministic checks and AI analysis assist in evidence quality; official dispute outcomes are determined by PayPal.
        </p>
      </footer>
    </main>
  )
}

// ─── Shipment & Manifest Management View ──────────────────────────────────────
function ShipmentsManifestView({ orders, activeShipmentId, setActiveShipmentId, navigateTo }) {
  const [manifest, setManifest] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [saveLoading, setSaveLoading] = useState(false)
  const [finalizeLoading, setFinalizeLoading] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState('')

  // Form draft state for editing/creating items
  const [draftItems, setDraftItems] = useState([
    { sku: '', description: '', expected_qty: 1, unit_value: '', fragile: false }
  ])
  const [draftNotes, setDraftNotes] = useState('')

  const selectedShipment = useMemo(() => {
    return orders.find(o => o.order_id === activeShipmentId) || orders[0] || null
  }, [orders, activeShipmentId])

  // Load manifest when activeShipmentId changes
  useEffect(() => {
    let ignore = false
    async function fetchManifest() {
      if (!selectedShipment) return
      setLoading(true)
      setError('')
      setSaveSuccess('')
      try {
        const res = await fetch(`${API_BASE}/api/shipments/${selectedShipment.order_id}/manifest`)
        if (ignore) return
        if (res.status === 404) {
          setManifest(null)
          setDraftItems([
            { sku: '', description: '', expected_qty: 1, unit_value: '', fragile: false }
          ])
          setDraftNotes('')
        } else if (!res.ok) {
          const data = await res.json().catch(() => ({}))
          throw new Error(data.detail || 'Could not load manifest')
        } else {
          const data = await res.json()
          if (ignore) return
          setManifest(data)
          setDraftItems(
            data.items.map(it => ({
              id: it.id,
              sku: it.sku || '',
              description: it.description || '',
              expected_qty: it.expected_qty,
              unit_value: it.unit_value_cents !== null && it.unit_value_cents !== undefined
                ? (it.unit_value_cents / 100).toFixed(2)
                : '',
              fragile: Boolean(it.fragile)
            }))
          )
          setDraftNotes(data.notes || '')
        }
      } catch (err) {
        if (!ignore) setError(err.message || 'Error loading manifest')
      } finally {
        if (!ignore) setLoading(false)
      }
    }

    fetchManifest()
    return () => {
      ignore = true
    }
  }, [selectedShipment?.order_id]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleAddItem() {
    setDraftItems(prev => [
      ...prev,
      { sku: '', description: '', expected_qty: 1, unit_value: '', fragile: false }
    ])
  }

  function handleRemoveItem(index) {
    if (draftItems.length <= 1) return
    setDraftItems(prev => prev.filter((_, idx) => idx !== index))
  }

  function handleItemChange(index, field, value) {
    setDraftItems(prev => {
      const updated = [...prev]
      updated[index] = { ...updated[index], [field]: value }
      return updated
    })
  }

  async function handleSaveManifest() {
    if (!selectedShipment) return
    setError('')
    setSaveSuccess('')

    // Strict validation
    for (let i = 0; i < draftItems.length; i++) {
      const it = draftItems[i]
      if (!it.description.trim()) {
        setError(`Item #${i + 1}: Description is required.`)
        return
      }

      // Quantity validation using Number.isSafeInteger to reject fractional, NaN, zero, and negative
      const rawQty = it.expected_qty
      if (typeof rawQty === 'string' && rawQty.trim() === '') {
        setError(`Item #${i + 1}: Expected quantity is required.`)
        return
      }
      const numQty = Number(rawQty)
      if (!Number.isSafeInteger(numQty) || numQty <= 0) {
        setError(`Item #${i + 1}: Expected quantity must be a positive integer (received "${rawQty}").`)
        return
      }

      // Unit value validation: finite, non-negative number before converting to cents
      if (it.unit_value !== '' && it.unit_value !== null && it.unit_value !== undefined) {
        const valStr = String(it.unit_value).trim()
        if (valStr !== '') {
          const numVal = Number(valStr)
          if (!Number.isFinite(numVal) || numVal < 0) {
            setError(`Item #${i + 1}: Unit value must be a finite, non-negative number (received "${it.unit_value}").`)
            return
          }
        }
      }
    }

    const payloadItems = draftItems.map(it => {
      const numQty = Number(it.expected_qty)
      const valStr = it.unit_value !== '' && it.unit_value !== null && it.unit_value !== undefined ? String(it.unit_value).trim() : ''
      const parsedUnitValue = valStr !== '' && Number.isFinite(Number(valStr))
        ? Math.round(Number(valStr) * 100)
        : null

      return {
        sku: it.sku?.trim() || null,
        description: it.description.trim(),
        expected_qty: numQty,
        unit_value_cents: parsedUnitValue,
        fragile: Boolean(it.fragile)
      }
    })

    const payload = {
      items: payloadItems,
      notes: draftNotes.trim() || null
    }

    setSaveLoading(true)
    try {
      let res
      if (manifest && manifest.id && manifest.status === 'DRAFT') {
        // Update existing DRAFT
        res = await fetch(`${API_BASE}/api/manifests/${manifest.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
      } else {
        // Create initial manifest for this shipment
        res = await fetch(`${API_BASE}/api/shipments/${selectedShipment.order_id}/manifest`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
      }

      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to save manifest')
      }

      setManifest(data)
      setSaveSuccess('Manifest saved as DRAFT successfully.')
      setTimeout(() => setSaveSuccess(''), 3000)
    } catch (err) {
      setError(err.message || 'Error saving manifest.')
    } finally {
      setSaveLoading(false)
    }
  }

  async function handleFinalizeManifest() {
    if (!manifest || !manifest.id) return
    setError('')
    setSaveSuccess('')
    setFinalizeLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/manifests/${manifest.id}/finalize`, {
        method: 'POST'
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to finalize manifest')
      }
      setManifest(data)
      setSaveSuccess('Manifest FINALIZED! Cryptographic SHA-256 fingerprint generated.')
    } catch (err) {
      setError(err.message || 'Error finalizing manifest.')
    } finally {
      setFinalizeLoading(false)
    }
  }

  const isFinalized = manifest?.status === 'FINALIZED'
  const manifestTotalValue = draftItems.reduce((acc, it) => {
    const val = parseFloat(it.unit_value) || 0
    const qty = parseInt(it.expected_qty, 10) || 0
    return acc + (val * qty)
  }, 0)

  return (
    <main className="main" id="main-content">
      <header className="topbar">
        <div className="breadcrumb">
          <span>Workspace</span>
          <span>/</span>
          <strong>Shipment Management &amp; Manifests</strong>
        </div>
        <div className="topbar-actions">
          <button
            className="btn-secondary"
            onClick={() => navigateTo('/')}
          >
            ← Back to Evidence Review
          </button>
        </div>
      </header>

      <div className="manifest-layout">
        {/* Left: Shipment Selector List */}
        <aside className="manifest-shipments-sidebar" aria-label="Select Shipment">
          <div className="sidebar-section-title">
            <span>ACTIVE SHIPMENTS</span>
            <small>{orders.length} Records</small>
          </div>
          <div className="manifest-shipment-cards">
            {orders.map(order => {
              const isSelected = selectedShipment?.order_id === order.order_id
              return (
                <button
                  key={order.order_id}
                  className={`manifest-shipment-card ${isSelected ? 'active' : ''}`}
                  onClick={() => {
                    setActiveShipmentId(order.order_id)
                  }}
                >
                  <div className="m-card-top">
                    <strong>{order.order_id}</strong>
                    <span className="m-card-status">{order.status}</span>
                  </div>
                  <div className="m-card-details">
                    <span>Carrier: {order.carrier || 'N/A'}</span>
                    <span>Tracking: {order.tracking_number ? `${order.tracking_number.slice(0, 10)}…` : 'Missing'}</span>
                  </div>
                  <div className="m-card-dest">{order.shipping_address || 'No destination'}</div>
                </button>
              )
            })}
          </div>
        </aside>

        {/* Right: Manifest Editor & Details */}
        <section className="manifest-editor-panel" aria-label="Manifest Details">
          {selectedShipment ? (
            <>
              {/* Shipment Header Banner */}
              <div className="manifest-header-card">
                <div className="m-header-left">
                  <div className="eyebrow">SHIPMENT PRODUCT MANIFEST</div>
                  <h2>{selectedShipment.order_id}</h2>
                  <p>
                    Carrier: <strong>{selectedShipment.carrier || 'Unspecified'}</strong> ·
                    Txn: <code>{selectedShipment.transaction_id || selectedShipment.paypal_capture_id || '—'}</code> ·
                    Order Total: <strong>${Number(selectedShipment.amount || 0).toFixed(2)} {selectedShipment.currency || 'USD'}</strong>
                    {selectedShipment.checkout_order_id && (
                      <> · Order: <code>{selectedShipment.checkout_order_id.slice(0, 8)}…</code></>
                    )}
                  </p>
                </div>
                <div className="m-header-right">
                  {manifest ? (
                    <div className="manifest-status-badge-wrap">
                      <span className={`pill ${isFinalized ? 'pill-pass' : 'pill-warn'}`}>
                        {manifest.status}
                      </span>
                      {isFinalized && (
                        <div className="finalized-lock-tag">
                          <LockIcon /> Sealed &amp; Hashed
                        </div>
                      )}
                    </div>
                  ) : (
                    <span className="pill pill-unchecked">NO MANIFEST</span>
                  )}
                </div>
              </div>

              {/* SHA-256 Fingerprint Callout for Finalized Manifests */}
              {isFinalized && manifest.manifest_hash && (
                <div className="hash-display-banner">
                  <div className="hash-info">
                    <span className="hash-label">CRYPTOGRAPHIC SHA-256 FINGERPRINT</span>
                    <code className="hash-code">{manifest.manifest_hash}</code>
                    <small className="hash-explanation">
                      Deterministic manifest hash binds declared items, quantities, and values. Manifest is immutably locked against tampering.
                    </small>
                  </div>
                  <button
                    className="btn-primary"
                    onClick={() => navigateTo('/packing', { shipmentId: selectedShipment.order_id })}
                  >
                    Open in Packing Station →
                  </button>
                </div>
              )}

              {/* Alert notifications */}
              {error && (
                <div className="findings-box issues" role="alert" style={{ marginBottom: '16px' }}>
                  {error}
                </div>
              )}
              {saveSuccess && (
                <div className="pass-callout" role="status" style={{ marginBottom: '16px' }}>
                  ✓ {saveSuccess}
                </div>
              )}

              {/* Manifest Items Table / Form */}
              <div className="manifest-items-card">
                <div className="items-card-header">
                  <div>
                    <h3>Declared Manifest Items</h3>
                    <p>Enter the SKUs, item descriptions, expected shipment quantities, and declared fragile status.</p>
                  </div>
                  <div className="items-header-stats">
                    <span className="stat-pill">Items: {draftItems.length}</span>
                    <span className="stat-pill">Est. Value: ${manifestTotalValue.toFixed(2)}</span>
                  </div>
                </div>

                {loading ? (
                  <div className="checkout-state-box" style={{ padding: '30px' }} role="status">
                    <div className="checkout-state-icon loading-spinner"><SpinnerIcon /></div>
                    <p>Loading manifest details…</p>
                  </div>
                ) : (
                  <>
                    <div className="manifest-table-wrap">
                      <table className="manifest-table">
                        <thead>
                          <tr>
                            <th style={{ width: '40px' }}>#</th>
                            <th style={{ width: '130px' }}>SKU</th>
                            <th>Description *</th>
                            <th style={{ width: '100px' }}>Qty *</th>
                            <th style={{ width: '120px' }}>Unit Value ($)</th>
                            <th style={{ width: '80px' }}>Fragile</th>
                            {!isFinalized && <th style={{ width: '60px' }}>Action</th>}
                          </tr>
                        </thead>
                        <tbody>
                          {draftItems.map((item, idx) => (
                            <tr key={idx}>
                              <td className="row-num">{idx + 1}</td>
                              <td>
                                {isFinalized ? (
                                  <span className="field-readonly">{item.sku || '—'}</span>
                                ) : (
                                  <input
                                    type="text"
                                    className="form-control"
                                    value={item.sku}
                                    placeholder="SKU-100"
                                    onChange={e => handleItemChange(idx, 'sku', e.target.value)}
                                  />
                                )}
                              </td>
                              <td>
                                {isFinalized ? (
                                  <span className="field-readonly">{item.description}</span>
                                ) : (
                                  <input
                                    type="text"
                                    className="form-control"
                                    value={item.description}
                                    placeholder="Product description…"
                                    onChange={e => handleItemChange(idx, 'description', e.target.value)}
                                  />
                                )}
                              </td>
                              <td>
                                {isFinalized ? (
                                  <span className="field-readonly bold">{item.expected_qty}</span>
                                ) : (
                                  <input
                                    type="number"
                                    min="1"
                                    step="1"
                                    className="form-control text-center"
                                    value={item.expected_qty}
                                    onChange={e => handleItemChange(idx, 'expected_qty', e.target.value)}
                                  />
                                )}
                              </td>
                              <td>
                                {isFinalized ? (
                                  <span className="field-readonly">
                                    {item.unit_value ? `$${parseFloat(item.unit_value).toFixed(2)}` : '—'}
                                  </span>
                                ) : (
                                  <input
                                    type="number"
                                    min="0"
                                    step="0.01"
                                    className="form-control text-right"
                                    placeholder="0.00"
                                    value={item.unit_value}
                                    onChange={e => handleItemChange(idx, 'unit_value', e.target.value)}
                                  />
                                )}
                              </td>
                              <td style={{ textAlign: 'center' }}>
                                {isFinalized ? (
                                  item.fragile ? <span className="tag-fragile">FRAGILE</span> : <span className="text-muted">—</span>
                                ) : (
                                  <input
                                    type="checkbox"
                                    checked={item.fragile}
                                    onChange={e => handleItemChange(idx, 'fragile', e.target.checked)}
                                    className="fragile-checkbox"
                                  />
                                )}
                              </td>
                              {!isFinalized && (
                                <td style={{ textAlign: 'center' }}>
                                  <button
                                    type="button"
                                    className="btn-trash"
                                    onClick={() => handleRemoveItem(idx)}
                                    disabled={draftItems.length <= 1}
                                    title="Remove item"
                                  >
                                    ✕
                                  </button>
                                </td>
                              )}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {!isFinalized && (
                      <div className="add-row-action">
                        <button
                          type="button"
                          className="btn-secondary"
                          onClick={handleAddItem}
                        >
                          + Add Item Row
                        </button>
                      </div>
                    )}

                    {/* Manifest Notes */}
                    <div className="form-group" style={{ marginTop: '20px' }}>
                      <label htmlFor="manifest-notes">Packing / Dispatch Notes (Optional)</label>
                      {isFinalized ? (
                        <div className="field-readonly-box">{draftNotes || 'No notes provided.'}</div>
                      ) : (
                        <textarea
                          id="manifest-notes"
                          className="form-control"
                          rows="2"
                          placeholder="e.g. Dual-wall cardboard box, tamper-evident tape applied, fragile markings on exterior."
                          value={draftNotes}
                          onChange={e => setDraftNotes(e.target.value)}
                        />
                      )}
                    </div>

                    {/* Manifest Action Bar */}
                    <div className="manifest-actions-bar">
                      <div className="manifest-actions-info">
                        {isFinalized ? (
                          <span className="text-muted">
                            Manifest finalized on {new Date(manifest.updated_at).toLocaleString()}. Items cannot be modified.
                          </span>
                        ) : (
                          <span className="text-muted">
                            Save changes as a draft, or finalize to compute SHA-256 fingerprint for packing station.
                          </span>
                        )}
                      </div>
                      <div className="manifest-actions-buttons">
                        {!isFinalized ? (
                          <>
                            <button
                              type="button"
                              className="btn-secondary"
                              onClick={handleSaveManifest}
                              disabled={saveLoading || finalizeLoading}
                            >
                              {saveLoading ? 'Saving Draft…' : 'Save Draft'}
                            </button>
                            <button
                              type="button"
                              className="btn-primary"
                              onClick={handleFinalizeManifest}
                              disabled={saveLoading || finalizeLoading || !manifest}
                              title={!manifest ? 'Please save as draft first' : 'Finalize and generate SHA-256 fingerprint'}
                            >
                              {finalizeLoading ? 'Finalizing…' : 'Finalize & Fingerprint'}
                            </button>
                          </>
                        ) : (
                          <button
                            type="button"
                            className="btn-primary"
                            onClick={() => navigateTo('/packing', { shipmentId: selectedShipment.order_id })}
                          >
                            Proceed to Packing Station →
                          </button>
                        )}
                      </div>
                    </div>
                  </>
                )}
              </div>
            </>
          ) : (
            <div className="checkout-state-box" style={{ padding: '60px' }}>
              <p>No shipments available.</p>
            </div>
          )}
        </section>
      </div>
    </main>
  )
}

// ─── Packing Station Workflow View ────────────────────────────────────────────
function PackingStationView({ orders, activeShipmentId, setActiveShipmentId, navigateTo }) {
  const [manifest, setManifest] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Upload state
  const [selectedPhotos, setSelectedPhotos] = useState([]) // array of { file, previewUrl, id, sizeFormatted }
  const [photoShipmentId, setPhotoShipmentId] = useState(null)
  const [uploadError, setUploadError] = useState('')
  const [uploading, setUploading] = useState(false)
  const [processingStatus, setProcessingStatus] = useState('') // 'uploading' | 'analyzing'
  const [inspectionResult, setInspectionResult] = useState(null)

  const selectedShipment = useMemo(() => {
    return orders.find(o => o.order_id === activeShipmentId) || orders[0] || null
  }, [orders, activeShipmentId])

  // Synchronize photosRef inside an effect instead of render
  const photosRef = React.useRef([])
  useEffect(() => {
    photosRef.current = selectedPhotos
  }, [selectedPhotos])

  // Cleanup object URLs on unmount
  useEffect(() => {
    return () => {
      for (const p of photosRef.current) {
        if (p?.previewUrl) URL.revokeObjectURL(p.previewUrl)
      }
    }
  }, [])

  function switchShipment(orderId) {
    if (uploading) return
    // Revoke any existing object URLs
    for (const p of selectedPhotos) {
      if (p?.previewUrl) URL.revokeObjectURL(p.previewUrl)
    }
    setSelectedPhotos([])
    setPhotoShipmentId(null)
    setInspectionResult(null)
    setUploadError('')
    setProcessingStatus('')
    setManifest(null)
    setError('')
    setLoading(true)
    setActiveShipmentId(orderId)
  }

  // When selected shipment changes: clear existing photos/state and fetch its manifest
  const prevShipmentIdRef = React.useRef(selectedShipment?.order_id)
  useEffect(() => {
    if (prevShipmentIdRef.current !== selectedShipment?.order_id) {
      prevShipmentIdRef.current = selectedShipment?.order_id
      for (const p of photosRef.current) {
        if (p?.previewUrl) URL.revokeObjectURL(p.previewUrl)
      }
      setSelectedPhotos([])
      setPhotoShipmentId(null)
      setInspectionResult(null)
      setUploadError('')
      setProcessingStatus('')
      setManifest(null)
      setError('')
      setLoading(true)
    }

    let ignore = false
    async function fetchManifest() {
      if (!selectedShipment) return
      setLoading(true)
      setError('')
      try {
        const res = await fetch(`${API_BASE}/api/shipments/${selectedShipment.order_id}/manifest`)
        if (ignore) return
        if (res.status === 404) {
          setManifest(null)
        } else if (!res.ok) {
          const data = await res.json().catch(() => ({}))
          throw new Error(data.detail || 'Could not load manifest')
        } else {
          const data = await res.json()
          if (!ignore) setManifest(data)
        }
      } catch (err) {
        if (!ignore) setError(err.message || 'Error loading manifest')
      } finally {
        if (!ignore) setLoading(false)
      }
    }

    fetchManifest()
    return () => {
      ignore = true
    }
  }, [selectedShipment])

  // Format file size
  async function handleHumanReview(decision) {
    if (!inspectionDetail || reviewSaving) return
    const notes = reviewNotes.trim()
    if (decision !== 'APPROVED' && !notes) {
      setReviewError('Add a note explaining the rejection or requested correction.')
      return
    }
    setReviewSaving(true)
    setReviewError('')
    setReviewFeedback('')
    try {
      const res = await fetch(`${API_BASE}/api/inspections/${inspectionDetail.inspection_id}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          decision,
          reviewer_label: reviewerLabel.trim() || 'Merchant',
          notes
        })
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail) || 'Could not save the review decision.')
      }
      setInspectionDetail(prev => ({
        ...prev,
        inspection_status: data.inspection_status,
        review_history: data.review_history || [],
        updated_at: data.reviewed_at
      }))
      setInspectionsList(prev => prev.map(item =>
        item.inspection_id === data.inspection_id
          ? { ...item, inspection_status: data.inspection_status }
          : item
      ))
      setReviewNotes('')
      setReviewFeedback(`Human review recorded: ${data.inspection_status.replaceAll('_', ' ')}.`)
    } catch (err) {
      setReviewError(err.message || 'Could not save the review decision.')
    } finally {
      setReviewSaving(false)
    }
  }

  async function handleTrackingSubmit() {
    if (!selectedShipment || trackingSubmitting) return
    setTrackingSubmitting(true)
    setTrackingError('')
    setTrackingFeedback('')
    try {
      const res = await fetch(`${API_BASE}/api/shipments/${selectedShipment.order_id}/submit-tracking`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tracking_number: trackingNumber.trim(),
          carrier: trackingCarrier,
          carrier_name_other: trackingCarrier === 'OTHER' ? trackingCarrierOther.trim() : '',
          notify_payer: notifyPayer
        })
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail) || 'Could not submit tracking to PayPal.')
      }
      setOrders(prev => prev.map(order =>
        order.order_id === selectedShipment.order_id
          ? {
              ...order,
              tracking_number: data.tracking_number || trackingNumber.trim(),
              carrier: data.carrier || trackingCarrier,
              carrier_name_other: trackingCarrier === 'OTHER' ? trackingCarrierOther.trim() : 'UNASSIGNED',
              status: 'SHIPPED',
              tracking_submission_status: 'SUBMITTED',
              paypal_tracking_submitted_at: data.submitted_at || order.paypal_tracking_submitted_at
            }
          : order
      ))
      setTrackingFeedback(data.already_submitted
        ? 'This tracking number was already submitted to PayPal.'
        : 'Tracking successfully submitted to PayPal Sandbox.')
    } catch (err) {
      setTrackingError(err.message || 'Could not submit tracking to PayPal.')
    } finally {
      setTrackingSubmitting(false)
    }
  }

  function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
  }

  // Handle local photo selection with validation
  function handlePhotoSelect(e) {
    setUploadError('')
    const files = Array.from(e.target.files || [])
    if (!files.length) return

    const maxAllowed = 5
    if (selectedPhotos.length + files.length > maxAllowed) {
      setUploadError(`Maximum 5 photos allowed per inspection. You currently have ${selectedPhotos.length} selected.`)
      return
    }

    const acceptedTypes = ['image/jpeg', 'image/png', 'image/webp']
    const maxBytes = 10 * 1024 * 1024 // 10MB

    const newItems = []
    for (const f of files) {
      if (!acceptedTypes.includes(f.type)) {
        setUploadError(`File '${f.name}' has unsupported format. Only JPEG, PNG, and WebP images are allowed.`)
        return
      }
      if (f.size > maxBytes) {
        setUploadError(`File '${f.name}' exceeds the 10 MB per-file limit (${formatBytes(f.size)}).`)
        return
      }
      newItems.push({
        file: f,
        previewUrl: URL.createObjectURL(f),
        id: Math.random().toString(36).substring(2, 9),
        name: f.name,
        sizeFormatted: formatBytes(f.size),
        sizeBytes: f.size
      })
    }

    setSelectedPhotos(prev => [...prev, ...newItems])
    setPhotoShipmentId(selectedShipment.order_id)
    // Reset file input value so same files can be re-selected if removed
    e.target.value = ''
  }

  function handleRemovePhoto(id) {
    setSelectedPhotos(prev => {
      const target = prev.find(p => p.id === id)
      if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl)
      const next = prev.filter(p => p.id !== id)
      if (next.length === 0) {
        setPhotoShipmentId(null)
      }
      return next
    })
  }

  async function handleSubmitInspection() {
    if (loading) {
      setUploadError('Please wait for the shipment manifest to finish loading.')
      return
    }
    if (!manifest || manifest.status !== 'FINALIZED') {
      setUploadError('A finalized manifest is required before submitting for packing inspection.')
      return
    }
    // Integrity check: Ensure manifest belongs to selected shipment
    if (!manifest.shipment_order_id || manifest.shipment_order_id !== selectedShipment.order_id) {
      setUploadError(`Manifest shipment mismatch: manifest belongs to ${manifest.shipment_order_id || 'unknown'}, but active shipment is ${selectedShipment.order_id}.`)
      return
    }
    if (selectedPhotos.length === 0) {
      setUploadError('Please select at least 1 photograph of the packing station.')
      return
    }
    // Fail-closed photo shipment check: must strictly match current shipment whenever photos are present
    if (!photoShipmentId || photoShipmentId !== selectedShipment.order_id) {
      setUploadError('The selected photographs do not match the current shipment. Please re-select photos.')
      return
    }

    setUploading(true)
    setUploadError('')
    setProcessingStatus('uploading')

    const formData = new FormData()
    for (const item of selectedPhotos) {
      formData.append('photos', item.file)
    }

    try {
      setProcessingStatus('analyzing')
      const res = await fetch(`${API_BASE}/api/manifests/${manifest.id}/inspections`, {
        method: 'POST',
        body: formData
      })

      const data = await res.json()
      if (!res.ok) {
        throw new Error(
          typeof data.detail === 'string'
            ? data.detail
            : JSON.stringify(data.detail) || 'Failed to complete packing inspection'
        )
      }

      setInspectionResult(data)
      setProcessingStatus('complete')
    } catch (err) {
      setUploadError(err.message || 'Inspection request failed. Make sure the backend and Gemini API are configured.')
    } finally {
      setUploading(false)
    }
  }

  const isManifestAssociated = Boolean(
    manifest &&
    manifest.shipment_order_id === selectedShipment.order_id
  )
  const isFinalized = isManifestAssociated && manifest?.status === 'FINALIZED'
  const canSelectPhotos = !loading && isFinalized && !uploading

  return (
    <main className="main" id="main-content">
      <header className="topbar">
        <div className="breadcrumb">
          <span>Workspace</span>
          <span>/</span>
          <strong>Packing Station &amp; Gemini Inspection</strong>
        </div>
        <div className="topbar-actions">
          <button className="btn-secondary" onClick={() => navigateTo('/manifests')}>
            ← Back to Manifests
          </button>
        </div>
      </header>

      <div className="packing-layout">
        {/* Left: Shipment selector */}
        <aside className="manifest-shipments-sidebar" aria-label="Select Shipment">
          <div className="sidebar-section-title">
            <span>SELECT SHIPMENT</span>
            <small>{orders.length} Records</small>
          </div>
          <div className="manifest-shipment-cards">
            {orders.map(order => {
              const isSelected = selectedShipment?.order_id === order.order_id
              return (
                <button
                  key={order.order_id}
                  className={`manifest-shipment-card ${isSelected ? 'active' : ''}`}
                  disabled={uploading}
                  title={uploading ? 'Inspection upload in progress — shipment switching disabled' : ''}
                  onClick={() => {
                    switchShipment(order.order_id)
                  }}
                >
                  <div className="m-card-top">
                    <strong>{order.order_id}</strong>
                    <span className="m-card-status">{order.status}</span>
                  </div>
                  <div className="m-card-details">
                    <span>Carrier: {order.carrier || 'N/A'}</span>
                    <span>Tracking: {order.tracking_number ? `${order.tracking_number.slice(0, 10)}…` : 'Missing'}</span>
                  </div>
                </button>
              )
            })}
          </div>
        </aside>

        {/* Right: Packing Station Workspace */}
        <section className="packing-main-panel" aria-label="Packing Station Area">
          {selectedShipment ? (
            <>
              {/* Manifest summary banner */}
              <div className="manifest-header-card">
                <div className="m-header-left">
                  <div className="eyebrow">PACKING VERIFICATION STATION</div>
                  <h2>{selectedShipment.order_id}</h2>
                  <p>
                    Carrier: <strong>{selectedShipment.carrier || 'Unspecified'}</strong> ·
                    Txn: <code>{selectedShipment.transaction_id}</code> ·
                    Order Total: <strong>${Number(selectedShipment.amount || 0).toFixed(2)} {selectedShipment.currency || 'USD'}</strong>
                  </p>
                </div>
                <div className="m-header-right">
                  {manifest ? (
                    <span className={`pill ${isFinalized ? 'pill-pass' : 'pill-warn'}`}>
                      {manifest.status}
                    </span>
                  ) : (
                    <span className="pill pill-unchecked">NO MANIFEST</span>
                  )}
                </div>
              </div>

              {loading ? (
                <div className="checkout-state-box" style={{ padding: '40px' }} role="status">
                  <div className="checkout-state-icon loading-spinner"><SpinnerIcon /></div>
                  <p>Checking manifest status for {selectedShipment.order_id}…</p>
                </div>
              ) : error ? (
                <div className="findings-box issues" role="alert">{error}</div>
              ) : !manifest ? (
                /* No Manifest Empty State */
                <div className="checkout-state-box" style={{ padding: '48px 24px' }}>
                  <div className="checkout-state-icon" style={{ background: 'var(--amber-bg)', color: 'var(--amber)' }}>
                    <AlertIcon />
                  </div>
                  <h3>No Product Manifest Found</h3>
                  <p style={{ maxWidth: '460px', margin: '0 auto' }}>
                    Shipment <strong>{selectedShipment.order_id}</strong> does not have a manifest yet.
                    A finalized product manifest is required before uploading packing photos for Gemini inspection.
                  </p>
                  <button
                    className="btn-primary"
                    style={{ marginTop: '14px' }}
                    onClick={() => navigateTo('/manifests', { shipmentId: selectedShipment.order_id })}
                  >
                    Create Product Manifest →
                  </button>
                </div>
              ) : !isFinalized ? (
                /* Manifest is DRAFT, not yet finalized */
                <div className="checkout-state-box" style={{ padding: '48px 24px' }}>
                  <div className="checkout-state-icon" style={{ background: 'var(--info-bg)', color: 'var(--cobalt)' }}>
                    <LockIcon />
                  </div>
                  <h3>Manifest Is In Draft Status</h3>
                  <p style={{ maxWidth: '460px', margin: '0 auto' }}>
                    This shipment has a manifest with <strong>{manifest.items?.length || 0} items</strong>, but it has not been finalized.
                    Finalization locks the manifest and generates the SHA-256 fingerprint required for packing station verification.
                  </p>
                  <button
                    className="btn-primary"
                    style={{ marginTop: '14px' }}
                    onClick={() => navigateTo('/manifests', { shipmentId: selectedShipment.order_id })}
                  >
                    Open &amp; Finalize Manifest →
                  </button>
                </div>
              ) : (
                /* Finalized Manifest — Packing Station Active */
                <div className="packing-station-workspace">
                  {/* Finalized Manifest Snapshot */}
                  <div className="hash-display-banner">
                    <div className="hash-info">
                      <span className="hash-label">FINALIZED MANIFEST SNAPSHOT · SHA-256</span>
                      <code className="hash-code">{manifest.manifest_hash}</code>
                      <small className="hash-explanation">
                        Inspection compares photo evidence directly against this cryptographic manifest fingerprint ({manifest.items?.length || 0} items declared).
                      </small>
                    </div>
                    <span className="finalized-lock-tag">
                      <LockIcon /> Manifest Locked
                    </span>
                  </div>

                  {/* Declared items preview */}
                  <div className="declared-items-preview">
                    <strong>Declared Items for Inspection:</strong>
                    <div className="declared-items-chips">
                      {manifest.items?.map((it, i) => (
                        <span key={i} className="declared-chip">
                          <span className="chip-qty">{it.expected_qty}x</span>
                          <span className="chip-desc">{it.description}</span>
                          {it.sku && <span className="chip-sku">{it.sku}</span>}
                          {it.fragile && <span className="chip-fragile">FRAGILE</span>}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Upload Notification / Errors */}
                  {uploadError && (
                    <div className="findings-box issues" role="alert" style={{ marginBottom: '16px' }}>
                      {uploadError}
                    </div>
                  )}

                  {/* Success Banner when inspection is completed in this session */}
                  {inspectionResult && (
                    <div className="pass-callout" role="status" style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div>
                        <strong>✓ Gemini Packing Inspection Completed!</strong>
                        <p style={{ margin: '4px 0 0', fontSize: '11px' }}>
                          Status: <strong>{inspectionResult.inspection_status}</strong> · {inspectionResult.photo_count} photos evaluated with model <code>{inspectionResult.model_used}</code>.
                        </p>
                      </div>
                      <button
                        className="btn-primary"
                        style={{ fontSize: '11px', padding: '6px 12px' }}
                        onClick={() => navigateTo('/inspections', { shipmentId: selectedShipment.order_id })}
                      >
                        View AI Inspection &amp; Human Review →
                      </button>
                    </div>
                  )}

                  {/* Photo Dropzone / Upload Area */}
                  <div className="photo-upload-container">
                    <div className="upload-header">
                      <div>
                        <h3>Packing Evidence Photographs</h3>
                        <p>Upload 1 to 5 packing station photos (JPEG, PNG, WebP · max 10MB each) showing contents, container, and protective wrap.</p>
                      </div>
                      <span className="pill pill-unchecked">
                        {selectedPhotos.length} / 5 Photos
                      </span>
                    </div>

                    {/* Hidden file input */}
                    <input
                      type="file"
                      id="packing-photo-input"
                      multiple
                      accept="image/jpeg,image/png,image/webp"
                      style={{ display: 'none' }}
                      onChange={handlePhotoSelect}
                      disabled={!canSelectPhotos || selectedPhotos.length >= 5}
                    />

                    {selectedPhotos.length < 5 && canSelectPhotos && (
                      <label htmlFor="packing-photo-input" className="photo-dropzone">
                        <div className="dropzone-icon">
                          <CameraIcon />
                        </div>
                        <span className="dropzone-title">Click to upload packing station photos</span>
                        <small className="dropzone-sub">
                          Supported: JPEG, PNG, WebP up to 10MB.
                        </small>
                      </label>
                    )}

                    {/* Thumbnails of selected photos */}
                    {selectedPhotos.length > 0 && (
                      <div className="selected-photos-grid">
                        {selectedPhotos.map((photo) => (
                          <div key={photo.id} className="photo-thumb-card">
                            <div className="thumb-preview-wrap">
                              <img src={photo.previewUrl} alt={photo.name} className="thumb-img" />
                              {!uploading && (
                                <button
                                  type="button"
                                  className="btn-remove-thumb"
                                  onClick={() => handleRemovePhoto(photo.id)}
                                  title="Remove photo"
                                >
                                  ✕
                                </button>
                              )}
                            </div>
                            <div className="thumb-meta">
                              <span className="thumb-name" title={photo.name}>{photo.name}</span>
                              <span className="thumb-size">{photo.sizeFormatted}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Upload / Processing State Indicator */}
                    {uploading && (
                      <div className="processing-indicator-box" role="status" aria-live="polite">
                        <div className="checkout-state-icon loading-spinner">
                          <SpinnerIcon />
                        </div>
                        <div className="processing-info">
                          <strong>
                            {processingStatus === 'uploading'
                              ? 'Uploading photographs to private storage…'
                              : 'Gemini Vision AI inspecting shipment contents against manifest…'}
                          </strong>
                          <p>
                            Validating image magic bytes, extracting item counts, checking for visible packaging defects, and binding inspection to SHA-256 fingerprint snapshot.
                          </p>
                        </div>
                      </div>
                    )}

                    {/* Submit Inspection Button */}
                    <div className="upload-submit-actions">
                      <button
                        type="button"
                        className="btn-secondary"
                        onClick={() => navigateTo('/inspections', { shipmentId: selectedShipment.order_id })}
                        disabled={uploading}
                      >
                        Inspect History ↗
                      </button>
                      <button
                        type="button"
                        className="btn-primary"
                        onClick={handleSubmitInspection}
                        disabled={loading || !canSelectPhotos || uploading || selectedPhotos.length === 0}
                      >
                        {uploading
                          ? 'Processing AI Inspection…'
                          : `Run Gemini Inspection (${selectedPhotos.length} Photo${selectedPhotos.length === 1 ? '' : 's'})`}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="checkout-state-box" style={{ padding: '60px' }}>
              <p>No shipments available.</p>
            </div>
          )}
        </section>
      </div>
    </main>
  )
}

// ─── AI Inspection Results & Human Review View ────────────────────────────────
function InspectionsReviewView({ orders, setOrders, activeShipmentId, setActiveShipmentId, navigateTo }) {
  const [manifest, setManifest] = useState(null)
  const [inspectionsList, setInspectionsList] = useState([])
  const [activeInspectionId, setActiveInspectionId] = useState(null)
  const [inspectionDetail, setInspectionDetail] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [reviewerLabel, setReviewerLabel] = useState('Merchant')
  const [reviewNotes, setReviewNotes] = useState('')
  const [reviewSaving, setReviewSaving] = useState(false)
  const [reviewFeedback, setReviewFeedback] = useState('')
  const [reviewError, setReviewError] = useState('')
  const [trackingNumber, setTrackingNumber] = useState('')
  const [trackingCarrier, setTrackingCarrier] = useState('OTHER')
  const [trackingCarrierOther, setTrackingCarrierOther] = useState('')
  const [notifyPayer, setNotifyPayer] = useState(false)
  const [trackingSubmitting, setTrackingSubmitting] = useState(false)
  const [trackingFeedback, setTrackingFeedback] = useState('')
  const [trackingError, setTrackingError] = useState('')

  const selectedShipment = useMemo(() => {
    return orders.find(o => o.order_id === activeShipmentId) || orders[0] || null
  }, [orders, activeShipmentId])

  // Load manifest & inspections list whenever active shipment changes
  useEffect(() => {
    setReviewNotes('')
    setReviewFeedback('')
    setReviewError('')
    setTrackingNumber(selectedShipment?.tracking_number || '')
    setTrackingCarrier(selectedShipment?.carrier || 'OTHER')
    setTrackingCarrierOther(
      selectedShipment?.carrier === 'OTHER' && selectedShipment?.carrier_name_other !== 'UNASSIGNED'
        ? selectedShipment?.carrier_name_other || ''
        : ''
    )
    setTrackingFeedback('')
    setTrackingError('')
    let ignore = false
    async function fetchManifestAndInspections() {
      if (!selectedShipment) return
      setLoading(true)
      setError('')
      setManifest(null)
      setInspectionsList([])
      setActiveInspectionId(null)
      setInspectionDetail(null)

      try {
        const manRes = await fetch(`${API_BASE}/api/shipments/${selectedShipment.order_id}/manifest`)
        if (ignore) return
        if (manRes.status === 404) {
          setManifest(null)
          setLoading(false)
          return
        }
        if (!manRes.ok) {
          const data = await manRes.json().catch(() => ({}))
          throw new Error(data.detail || 'Could not load manifest')
        }

        const manData = await manRes.json()
        if (ignore) return
        setManifest(manData)

        // Fetch all inspections for this manifest
        const inspRes = await fetch(`${API_BASE}/api/manifests/${manData.id}/inspections`)
        if (ignore) return
        if (!inspRes.ok) {
          const inspErr = await inspRes.json().catch(() => ({}))
          throw new Error(inspErr.detail || 'Could not load inspection history')
        }

        const inspData = await inspRes.json()
        if (ignore) return
        const list = inspData.inspections || []
        setInspectionsList(list)

        if (list.length > 0) {
          setActiveInspectionId(list[0].inspection_id)
        }
      } catch (err) {
        if (!ignore) setError(err.message || 'Error loading inspections')
      } finally {
        if (!ignore) setLoading(false)
      }
    }

    fetchManifestAndInspections()
    return () => {
      ignore = true
    }
  }, [selectedShipment])

  // Fetch full inspection record whenever activeInspectionId changes
  useEffect(() => {
    let ignore = false
    async function fetchInspectionDetail() {
      if (!activeInspectionId) {
        setInspectionDetail(null)
        return
      }

      try {
        const res = await fetch(`${API_BASE}/api/inspections/${activeInspectionId}`)
        if (ignore) return
        if (!res.ok) {
          const data = await res.json().catch(() => ({}))
          throw new Error(data.detail || 'Could not load inspection detail')
        }
        const data = await res.json()
        if (!ignore) setInspectionDetail(data)
      } catch (err) {
        if (!ignore) setError(err.message || 'Failed to fetch inspection record')
      }
    }

    fetchInspectionDetail()
    return () => {
      ignore = true
    }
  }, [activeInspectionId])

  function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
  }

  const aiResult = inspectionDetail?.ai_result
  const itemChecks = aiResult?.item_checks || []
  const addlObs = aiResult?.additional_observations || {}
  const imageQuality = aiResult?.image_quality || {}
  const engineMeta = aiResult?.engine_metadata || {}
  const latestInspectionId = inspectionsList[0]?.inspection_id
  const isLatestInspection = Boolean(inspectionDetail && inspectionDetail.inspection_id === latestInspectionId)
  const canHumanReview = inspectionDetail?.inspection_status === 'PENDING_HUMAN_REVIEW'
  const canSubmitTracking =
    Boolean(selectedShipment?.checkout_order_id) &&
    isLatestInspection &&
    inspectionDetail?.inspection_status === 'APPROVED' &&
    selectedShipment?.tracking_submission_status !== 'SUBMITTED'

  return (
    <main className="main" id="main-content">
      <header className="topbar">
        <div className="breadcrumb">
          <span>Workspace</span>
          <span>/</span>
          <strong>AI Packing Inspection &amp; Human Review</strong>
        </div>
        <div className="topbar-actions">
          <button className="btn-secondary" onClick={() => navigateTo('/packing')}>
            ← Back to Packing Station
          </button>
        </div>
      </header>

      <div className="packing-layout">
        {/* Left: Shipment selector */}
        <aside className="manifest-shipments-sidebar" aria-label="Select Shipment">
          <div className="sidebar-section-title">
            <span>SELECT SHIPMENT</span>
            <small>{orders.length} Records</small>
          </div>
          <div className="manifest-shipment-cards">
            {orders.map(order => {
              const isSelected = selectedShipment?.order_id === order.order_id
              return (
                <button
                  key={order.order_id}
                  className={`manifest-shipment-card ${isSelected ? 'active' : ''}`}
                  onClick={() => {
                    setActiveShipmentId(order.order_id)
                  }}
                >
                  <div className="m-card-top">
                    <strong>{order.order_id}</strong>
                    <span className="m-card-status">{order.status}</span>
                  </div>
                  <div className="m-card-details">
                    <span>Carrier: {order.carrier || 'N/A'}</span>
                    <span>Tracking: {order.tracking_number ? `${order.tracking_number.slice(0, 10)}…` : 'Missing'}</span>
                  </div>
                </button>
              )
            })}
          </div>
        </aside>

        {/* Right: Inspection & Human Review Area */}
        <section className="packing-main-panel" aria-label="Human Review Area">
          {selectedShipment ? (
            <>
              {/* Shipment Header */}
              <div className="manifest-header-card">
                <div className="m-header-left">
                  <div className="eyebrow">PERSISTED GEMINI PACKING INSPECTION</div>
                  <h2>{selectedShipment.order_id}</h2>
                  <p>
                    Carrier: <strong>{selectedShipment.carrier || 'Unspecified'}</strong> ·
                    Txn: <code>{selectedShipment.transaction_id}</code> ·
                    Order Total: <strong>${Number(selectedShipment.amount || 0).toFixed(2)} {selectedShipment.currency || 'USD'}</strong>
                  </p>
                </div>
                <div className="m-header-right">
                  {inspectionDetail ? (
                    <span className="pill pill-warn" style={{ fontSize: '12px', padding: '8px 14px' }}>
                      {inspectionDetail.inspection_status}
                    </span>
                  ) : manifest ? (
                    <span className="pill pill-unchecked">{manifest.status}</span>
                  ) : (
                    <span className="pill pill-unchecked">NO MANIFEST</span>
                  )}
                </div>
              </div>

              {loading ? (
                <div className="checkout-state-box" style={{ padding: '40px' }} role="status">
                  <div className="checkout-state-icon loading-spinner"><SpinnerIcon /></div>
                  <p>Loading inspection records for {selectedShipment.order_id}…</p>
                </div>
              ) : error ? (
                <div className="findings-box issues" role="alert">{error}</div>
              ) : !manifest ? (
                <div className="checkout-state-box" style={{ padding: '48px 24px' }}>
                  <div className="checkout-state-icon" style={{ background: 'var(--amber-bg)', color: 'var(--amber)' }}>
                    <AlertIcon />
                  </div>
                  <h3>No Manifest or Inspections Found</h3>
                  <p style={{ maxWidth: '460px', margin: '0 auto' }}>
                    Shipment <strong>{selectedShipment.order_id}</strong> does not have a manifest yet. Create and finalize a manifest to run Gemini packing inspections.
                  </p>
                  <button
                    className="btn-primary"
                    style={{ marginTop: '14px' }}
                    onClick={() => navigateTo('/manifests', { shipmentId: selectedShipment.order_id })}
                  >
                    Go to Manifest Management →
                  </button>
                </div>
              ) : inspectionsList.length === 0 ? (
                <div className="checkout-state-box" style={{ padding: '48px 24px' }}>
                  <div className="checkout-state-icon" style={{ background: 'var(--info-bg)', color: 'var(--cobalt)' }}>
                    <CameraIcon />
                  </div>
                  <h3>No Inspection Records Found</h3>
                  <p style={{ maxWidth: '460px', margin: '0 auto' }}>
                    Manifest <code>{manifest.id.slice(0, 8)}…</code> is {manifest.status}, but no visual inspections have been run yet.
                  </p>
                  <button
                    className="btn-primary"
                    style={{ marginTop: '14px' }}
                    onClick={() => navigateTo('/packing', { shipmentId: selectedShipment.order_id })}
                  >
                    Launch Packing Station &amp; Upload Photos →
                  </button>
                </div>
              ) : (
                <div className="inspections-view-content">
                  {/* Human Review Banner - Prominent & Mandatory Safeguard */}
                  <div className="human-review-banner">
                    <div className="hr-shield-badge">
                      <ShieldIcon />
                    </div>
                    <div className="hr-banner-text">
                      <div className="hr-title-row">
                        <strong>STATUS: {inspectionDetail?.inspection_status || 'PENDING_HUMAN_REVIEW'}</strong>
                        <span className={`pill ${inspectionDetail?.inspection_status === 'APPROVED' ? 'pill-pass' : inspectionDetail?.inspection_status === 'REJECTED' ? 'pill-blocked' : 'pill-warn'}`}>
                          {inspectionDetail?.inspection_status === 'APPROVED'
                            ? 'HUMAN REVIEW APPROVED'
                            : inspectionDetail?.inspection_status === 'REJECTED'
                            ? 'REJECTED'
                            : inspectionDetail?.inspection_status === 'NEEDS_CORRECTION'
                            ? 'CORRECTION REQUIRED'
                            : 'HUMAN ACTION REQUIRED'}
                        </span>
                      </div>
                      <p>
                        Visual AI inspection is an advisory assistance tool. By system safety policy,
                        <strong> Gemini never automatically approves shipments</strong>. Merchant reviewers must inspect
                        the observed contents, discrepancies, packaging damage, and photo evidence below before making shipping decisions.
                      </p>
                    </div>
                  </div>

                  {/* Multi-inspection tabs if multiple runs exist */}
                  {inspectionsList.length > 1 && (
                    <div className="inspection-runs-bar">
                      <span className="runs-label">INSPECTION RUNS:</span>
                      {inspectionsList.map((insp, idx) => (
                        <button
                          key={insp.inspection_id}
                          className={`btn-run-tab ${activeInspectionId === insp.inspection_id ? 'active' : ''}`}
                          onClick={() => setActiveInspectionId(insp.inspection_id)}
                        >
                          Run #{inspectionsList.length - idx} ({new Date(insp.created_at).toLocaleTimeString()})
                        </button>
                      ))}
                    </div>
                  )}

                  {inspectionDetail && (
                    <>
                      {/* Inspection Metadata Bar */}
                      <div className="hash-display-banner">
                        <div className="hash-info">
                          <span className="hash-label">SNAPSHOT MANIFEST FINGERPRINT AT INSPECTION</span>
                          <code className="hash-code">{inspectionDetail.manifest_hash_at_inspection}</code>
                          <small className="hash-explanation">
                            Inspection ID: <code>{inspectionDetail.inspection_id}</code> ·
                            Model: <strong>{inspectionDetail.model_used}</strong> ·
                            Timestamp: {new Date(inspectionDetail.created_at).toLocaleString()}
                          </small>
                        </div>
                        <div className="insp-photo-badge">
                          {inspectionDetail.photo_count} Photo{inspectionDetail.photo_count === 1 ? '' : 's'} Evaluated
                        </div>
                      </div>

                      {/* AI Summary Card */}
                      {aiResult?.inspection_summary && (
                        <div className="ai-summary-callout">
                          <div className="summary-callout-header">
                            <span className="eyebrow" style={{ color: 'var(--cobalt)', margin: 0 }}>GEMINI INSPECTION SUMMARY</span>
                            <span className={`quality-badge q-${(imageQuality.overall || 'fair').toLowerCase()}`}>
                              Image Quality: {imageQuality.overall || 'UNKNOWN'}
                            </span>
                          </div>
                          <p className="summary-callout-body">{aiResult.inspection_summary}</p>
                        </div>
                      )}

                      {/* Expected vs Observed Quantities Table */}
                      <div className="manifest-items-card">
                        <div className="items-card-header">
                          <div>
                            <h3>Expected vs. Observed Shipment Goods Audit</h3>
                            <p>Actual Gemini vision observations matched against declared goods in the manifest fingerprint.</p>
                          </div>
                          <span className="stat-pill">{itemChecks.length} Items Checked</span>
                        </div>

                        <div className="manifest-table-wrap">
                          <table className="manifest-table">
                            <thead>
                              <tr>
                                <th style={{ width: '120px' }}>SKU</th>
                                <th>Item Description</th>
                                <th style={{ width: '90px', textAlign: 'center' }}>Expected</th>
                                <th style={{ width: '90px', textAlign: 'center' }}>Observed</th>
                                <th style={{ width: '130px', textAlign: 'center' }}>Result</th>
                                <th style={{ width: '100px', textAlign: 'center' }}>Confidence</th>
                                <th>Visual Evidence</th>
                              </tr>
                            </thead>
                            <tbody>
                              {itemChecks.map((chk, i) => {
                                const resultBadgeClass =
                                  chk.result === 'MATCH' ? 'pill-pass' :
                                  chk.result === 'POSSIBLE_MISSING' ? 'pill-blocked' :
                                  chk.result === 'POSSIBLE_EXTRA' ? 'pill-warn' :
                                  'pill-unchecked'

                                const confClass =
                                  chk.confidence === 'HIGH' ? 'score-chip high' :
                                  chk.confidence === 'MEDIUM' ? 'score-chip med' :
                                  'score-chip low'

                                return (
                                  <tr key={i}>
                                    <td className="field-readonly">{chk.sku || '—'}</td>
                                    <td>
                                      <strong>{chk.description}</strong>
                                    </td>
                                    <td style={{ textAlign: 'center' }} className="field-readonly bold">
                                      {chk.expected_qty}
                                    </td>
                                    <td style={{ textAlign: 'center' }}>
                                      <span className={`observed-qty-tag ${chk.observed_qty === null ? 'null-qty' : ''}`}>
                                        {chk.observed_qty === null ? 'Uncertain' : chk.observed_qty}
                                      </span>
                                    </td>
                                    <td style={{ textAlign: 'center' }}>
                                      <span className={`pill ${resultBadgeClass}`}>
                                        {chk.result}
                                      </span>
                                    </td>
                                    <td style={{ textAlign: 'center' }}>
                                      <span className={confClass} style={{ fontSize: '10px', padding: '2px 8px' }}>
                                        {chk.confidence}
                                      </span>
                                    </td>
                                    <td style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                                      {chk.visual_evidence || '—'}
                                    </td>
                                  </tr>
                                )
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>

                      {/* Observations Matrix: Damage, Extras, Uncertainties */}
                      <div className="observations-grid">
                        <div className="obs-card">
                          <h4>Visible Product Damage</h4>
                          {addlObs.visible_product_damage?.length > 0 ? (
                            <ul className="obs-list error-list">
                              {addlObs.visible_product_damage.map((d, i) => (
                                <li key={i}>⚠ {d}</li>
                              ))}
                            </ul>
                          ) : (
                            <p className="obs-none">✓ No visible product damage detected.</p>
                          )}
                        </div>

                        <div className="obs-card">
                          <h4>Visible Packaging Damage</h4>
                          {addlObs.visible_packaging_damage?.length > 0 ? (
                            <ul className="obs-list warn-list">
                              {addlObs.visible_packaging_damage.map((d, i) => (
                                <li key={i}>⚠ {d}</li>
                              ))}
                            </ul>
                          ) : (
                            <p className="obs-none">✓ Packaging appears intact without punctures or crushes.</p>
                          )}
                        </div>

                        <div className="obs-card">
                          <h4>Possible Extra Items</h4>
                          {addlObs.possible_extra_items?.length > 0 ? (
                            <ul className="obs-list warn-list">
                              {addlObs.possible_extra_items.map((ex, i) => (
                                <li key={i}>+ {ex}</li>
                              ))}
                            </ul>
                          ) : (
                            <p className="obs-none">None detected outside manifest.</p>
                          )}
                        </div>

                        <div className="obs-card">
                          <h4>Uncertainty &amp; Limitations</h4>
                          {addlObs.uncertainty_notes?.length > 0 ? (
                            <ul className="obs-list">
                              {addlObs.uncertainty_notes.map((u, i) => (
                                <li key={i}>• {u}</li>
                              ))}
                            </ul>
                          ) : (
                            <p className="obs-none">No explicit uncertainty notes logged.</p>
                          )}
                        </div>
                      </div>

                      {/* Photo Evidence Records (SHA-256 and Stored Metadata) */}
                      <div className="photo-records-card">
                        <div className="records-header">
                          <div>
                            <h3>Persisted Evidence Photographs</h3>
                            <p>
                              Photographs are validated against magic bytes and immutably recorded with cryptographic SHA-256 digests.
                            </p>
                          </div>
                          <span className="pill pill-unchecked">
                            {inspectionDetail.photos?.length || 0} Photos Recorded
                          </span>
                        </div>

                        <div className="evidence-records-grid">
                          {inspectionDetail.photos?.map((photo, i) => (
                            <div key={photo.id || i} className="evidence-record-item">
                              <div className="evidence-record-badge">Photo #{i + 1}</div>
                              <div className="evidence-record-fields">
                                <div className="ev-row">
                                  <span className="ev-label">SHA-256 Digest:</span>
                                  <code className="ev-hash" title={photo.sha256}>{photo.sha256}</code>
                                </div>
                                <div className="ev-row-split">
                                  <span>MIME: <strong>{photo.mime_type}</strong></span>
                                  <span>Size: <strong>{formatBytes(photo.size_bytes)}</strong></span>
                                </div>
                                <div className="ev-id-row">
                                  <small>Record ID: <code>{photo.id}</code></small>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Engine Disclosure Disclaimer */}
                      <div className="engine-disclosure-card">
                        <div className="disclosure-head">
                          <strong>AI Engine Specification: {engineMeta.type || 'GEMINI_VISION_LLM'} ({engineMeta.model || inspectionDetail.model_used})</strong>
                          <span className="hallucination-warning">Zero-Hallucination: False (LLM Inference)</span>
                        </div>
                        <p className="disclosure-body">
                          {engineMeta.disclaimer ||
                            'Visual inspection only. Sealed container contents are not verified. This result requires human review before any shipment approval or rejection decision is made.'}
                        </p>
                      </div>

                      <div className="manifest-items-card" style={{ marginTop: '18px' }}>
                        <div className="items-card-header">
                          <div>
                            <h3>Merchant Review Decision</h3>
                            <p>Review the original photos and AI observations. The decision is recorded separately; it never changes Gemini's result.</p>
                          </div>
                          <span className={`pill ${inspectionDetail.inspection_status === 'APPROVED' ? 'pill-pass' : inspectionDetail.inspection_status === 'REJECTED' ? 'pill-blocked' : 'pill-warn'}`}>
                            {inspectionDetail.inspection_status.replaceAll('_', ' ')}
                          </span>
                        </div>

                        {reviewFeedback && <div className="pass-callout" role="status">{reviewFeedback}</div>}
                        {reviewError && <div className="findings-box issues" role="alert">{reviewError}</div>}

                        {canHumanReview ? (
                          <div style={{ padding: '16px' }}>
                            <div className="form-group">
                              <label htmlFor="reviewer-label">Reviewer label</label>
                              <input
                                id="reviewer-label"
                                className="form-control"
                                value={reviewerLabel}
                                maxLength={100}
                                onChange={e => setReviewerLabel(e.target.value)}
                                placeholder="e.g. Merchant"
                              />
                              <small style={{ color: 'var(--text-muted)' }}>This is a demo label, not a verified login identity.</small>
                            </div>
                            <div className="form-group" style={{ marginTop: '12px' }}>
                              <label htmlFor="review-notes">Review notes</label>
                              <textarea
                                id="review-notes"
                                className="form-control"
                                rows="3"
                                maxLength={2000}
                                value={reviewNotes}
                                onChange={e => setReviewNotes(e.target.value)}
                                placeholder="Record what you checked, or explain what needs to be corrected."
                              />
                            </div>
                            <div className="remediation-actions" style={{ flexWrap: 'wrap', marginTop: '14px' }}>
                              <button className="btn-primary" disabled={reviewSaving || !reviewerLabel.trim()} onClick={() => handleHumanReview('APPROVED')}>
                                {reviewSaving ? 'Saving…' : 'Approve packing review'}
                              </button>
                              <button className="btn-secondary" disabled={reviewSaving || !reviewNotes.trim()} onClick={() => handleHumanReview('NEEDS_CORRECTION')}>
                                Request correction
                              </button>
                              <button className="btn-secondary" disabled={reviewSaving || !reviewNotes.trim()} onClick={() => handleHumanReview('REJECTED')}>
                                Reject inspection
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div style={{ padding: '16px' }}>
                            <p>
                              {inspectionDetail.inspection_status === 'APPROVED'
                                ? 'A merchant approved this inspection. A new inspection is required to record another review.'
                                : inspectionDetail.inspection_status === 'NEEDS_CORRECTION'
                                ? 'Corrections are required. Return to the packing station, capture updated evidence, and submit a new inspection.'
                                : 'This inspection was rejected. Submit a new inspection only after the underlying packing issue has been resolved.'}
                            </p>
                          </div>
                        )}

                        {(inspectionDetail.review_history || []).length > 0 && (
                          <div style={{ padding: '0 16px 16px' }}>
                            <h4>Review history</h4>
                            {inspectionDetail.review_history.map(review => (
                              <div key={review.id} className="evidence-record-item" style={{ marginTop: '8px' }}>
                                <strong>{review.decision.replaceAll('_', ' ')}</strong>
                                <p style={{ margin: '4px 0' }}>{review.notes || 'No additional notes.'}</p>
                                <small>{review.reviewer_label} · {new Date(review.created_at).toLocaleString()}</small>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>

                      {selectedShipment.checkout_order_id && (
                        <div className="manifest-items-card" style={{ marginTop: '18px' }}>
                          <div className="items-card-header">
                            <div>
                              <h3>Shipment Tracking &amp; PayPal Submission</h3>
                              <p>Tracking is unlocked only after the latest inspection is approved. PayPal receives the saved order and capture IDs plus the purchased items.</p>
                            </div>
                            <span className={`pill ${selectedShipment.tracking_submission_status === 'SUBMITTED' ? 'pill-pass' : 'pill-unchecked'}`}>
                              {(selectedShipment.tracking_submission_status || 'NOT_SUBMITTED').replaceAll('_', ' ')}
                            </span>
                          </div>

                          {selectedShipment.tracking_submission_status === 'SUBMITTED' ? (
                            <div className="pass-callout" role="status">
                              Tracking {selectedShipment.tracking_number} has been submitted to PayPal Sandbox.
                              {selectedShipment.paypal_tracking_submitted_at && <small style={{ display: 'block', marginTop: '4px' }}>{new Date(selectedShipment.paypal_tracking_submitted_at).toLocaleString()}</small>}
                            </div>
                          ) : canSubmitTracking ? (
                            <div style={{ padding: '16px' }}>
                              {trackingFeedback && <div className="pass-callout" role="status">{trackingFeedback}</div>}
                              {trackingError && <div className="findings-box issues" role="alert">{trackingError}</div>}
                              {selectedShipment.tracking_submission_status === 'FAILED' && (
                                <p className="findings-box warnings">The last PayPal submission failed. Check the details and retry. PayPal may already have received a request if the connection failed after sending; its Orders v2 tracking endpoint supports idempotent retries using the same capture and tracking IDs.</p>
                              )}
                              <div className="interactive-form-grid">
                                <div className="form-group">
                                  <label htmlFor="tracking-number">Carrier tracking number</label>
                                  <input id="tracking-number" className="form-control" maxLength={64} value={trackingNumber} onChange={e => setTrackingNumber(e.target.value)} placeholder="Enter the carrier tracking number" />
                                </div>
                                <div className="form-group">
                                  <label htmlFor="tracking-carrier">Carrier</label>
                                  <select id="tracking-carrier" className="form-control" value={trackingCarrier} onChange={e => setTrackingCarrier(e.target.value)}>
                                    <option value="FEDEX">FedEx</option>
                                    <option value="UPS">UPS</option>
                                    <option value="USPS">USPS</option>
                                    <option value="DHL">DHL</option>
                                    <option value="OTHER">Other carrier</option>
                                  </select>
                                </div>
                                {trackingCarrier === 'OTHER' && (
                                  <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                                    <label htmlFor="tracking-carrier-other">Carrier name</label>
                                    <input id="tracking-carrier-other" className="form-control" maxLength={64} value={trackingCarrierOther} onChange={e => setTrackingCarrierOther(e.target.value)} placeholder="e.g. Delhivery, Blue Dart" />
                                  </div>
                                )}
                                <div className="form-checkbox-row">
                                  <input id="notify-payer" type="checkbox" checked={notifyPayer} onChange={e => setNotifyPayer(e.target.checked)} />
                                  <label htmlFor="notify-payer" style={{ cursor: 'pointer' }}>Email the buyer PayPal tracking details</label>
                                </div>
                              </div>
                              <div className="remediation-actions" style={{ marginTop: '14px' }}>
                                <button className="btn-primary" disabled={trackingSubmitting || !trackingNumber.trim() || (trackingCarrier === 'OTHER' && !trackingCarrierOther.trim())} onClick={handleTrackingSubmit}>
                                  {trackingSubmitting ? 'Submitting to PayPal…' : 'Submit tracking to PayPal'}
                                </button>
                              </div>
                              <small style={{ display: 'block', marginTop: '10px', color: 'var(--text-muted)' }}>
                                Sandbox only. The local PayPal tracking write gate must be explicitly enabled before any external submission.
                              </small>
                            </div>
                          ) : (
                            <div style={{ padding: '16px' }}>
                              {trackingError && <div className="findings-box issues" role="alert">{trackingError}</div>}
                              <p>
                                {inspectionDetail.inspection_status !== 'APPROVED'
                                  ? 'Approve the latest inspection before submitting shipment tracking.'
                                  : 'The latest inspection must be the selected inspection, and the local PayPal write gate must be enabled.'}
                              </p>
                            </div>
                          )}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </>
          ) : (
            <div className="checkout-state-box" style={{ padding: '60px' }}>
              <p>No shipments available.</p>
            </div>
          )}
        </section>
      </div>
    </main>
  )
}

// ─── Checkout Catalog View ────────────────────────────────────────────────────
function CheckoutCatalogView({
  catalog,
  catalogLoading,
  catalogError,
  cart,
  checkoutLoading,
  checkoutError,
  checkoutDetails,
  setCheckoutDetails,
  loadCatalog,
  addToCart,
  removeFromCart,
  getCartItems,
  getCartTotal,
  handleCheckout,
  navigateTo
}) {
  const cartItemCount = getCartItems().reduce((s, i) => s + i.quantity, 0)
  const cartTotal = getCartTotal()
  const hasItems = cartItemCount > 0
  const regionRequiredCountries = ['AR', 'BR', 'CA', 'CN', 'ID', 'IN', 'JP', 'MX', 'TH', 'US']
  const regionRequired = regionRequiredCountries.includes(
    checkoutDetails.countryCode.trim().toUpperCase()
  )

  return (
    <main className="main" id="main-content">
      <header className="topbar">
        <div className="breadcrumb">
          <span>Workspace</span>
          <span>/</span>
          <strong>New Checkout</strong>
        </div>
        <div className="topbar-actions">
          <button
            className="btn-secondary"
            onClick={() => navigateTo('/')}
            aria-label="Back to Shipment Review dashboard"
          >
            ← Back to Shipment Review
          </button>
        </div>
      </header>

      <div className="checkout-layout">
        <section className="checkout-catalog-section" aria-labelledby="catalog-heading">
          <div className="queue-header" style={{ marginBottom: '20px' }}>
            <div className="queue-title">
              <div className="eyebrow">PRODUCT CATALOGUE</div>
              <h1 id="catalog-heading" className="checkout-page-heading">Shop physical products</h1>
              <p>Choose items from the demo store. Your paid order will carry these exact products into the merchant's packing manifest.</p>
            </div>
          </div>

          {catalogLoading ? (
            <div className="checkout-state-box" role="status" aria-live="polite">
              <div className="checkout-state-icon loading-spinner" aria-hidden="true">
                <SpinnerIcon />
              </div>
              <p>Loading product catalogue…</p>
            </div>
          ) : catalogError ? (
            <div className="checkout-state-box checkout-state-error" role="alert">
              <div className="checkout-state-icon error-icon" aria-hidden="true">
                <AlertIcon />
              </div>
              <p>{catalogError}</p>
              <button className="btn-primary" onClick={loadCatalog}>
                Retry
              </button>
            </div>
          ) : catalog.length === 0 ? (
            <div className="checkout-state-box" role="status">
              <p>No products available at the moment.</p>
            </div>
          ) : (
            <div className="catalog-grid">
              {catalog.map(product => {
                const qty = cart[product.sku] || 0
                return (
                  <article key={product.sku} className="catalog-card">
                    <div className="catalog-card-body">
                      <div className="catalog-card-sku">{product.sku}</div>
                      <h2 className="catalog-card-name">{product.name}</h2>
                      <p className="catalog-card-desc">{product.description}</p>
                    </div>
                    <div className="catalog-card-footer">
                      <div className="catalog-card-price" aria-label={`Price: $${parseFloat(product.price).toFixed(2)} USD`}>
                        <span className="price-amount">${parseFloat(product.price).toFixed(2)}</span>
                        <span className="price-currency">USD</span>
                      </div>
                      <div className="qty-controls" role="group" aria-label={`Quantity for ${product.name}`}>
                        <button
                          className="qty-btn"
                          onClick={() => removeFromCart(product.sku)}
                          disabled={qty === 0}
                          aria-label={`Decrease quantity of ${product.name}`}
                        >
                          −
                        </button>
                        <span className="qty-value" aria-live="polite" aria-atomic="true">{qty}</span>
                        <button
                          className="qty-btn"
                          onClick={() => addToCart(product.sku)}
                          aria-label={`Increase quantity of ${product.name}`}
                        >
                          +
                        </button>
                      </div>
                    </div>
                  </article>
                )
              })}
            </div>
          )}
        </section>

        <aside className="checkout-summary-panel" aria-labelledby="summary-heading">
          <div className="summary-header">
            <h2 id="summary-heading" className="summary-title">Order Summary</h2>
            <span className="summary-badge">
              {cartItemCount} {cartItemCount === 1 ? 'item' : 'items'}
            </span>
          </div>

          {hasItems ? (
            <>
              <ul className="summary-line-items" aria-label="Cart contents">
                {getCartItems().map(({ sku, quantity }) => {
                  const product = catalog.find(p => p.sku === sku)
                  if (!product) return null
                  const lineTotal = (parseFloat(product.price) * quantity).toFixed(2)
                  return (
                    <li key={sku} className="summary-line-item">
                      <div className="summary-line-name">
                        <span className="summary-line-product">{product.name}</span>
                        <span className="summary-line-sku">{product.sku}</span>
                      </div>
                      <div className="summary-line-right">
                        <span className="summary-line-qty">× {quantity}</span>
                        <span className="summary-line-total">${lineTotal}</span>
                      </div>
                    </li>
                  )
                })}
              </ul>

              <div className="summary-total-row">
                <div>
                  <div className="summary-total-label">Estimated Total</div>
                  <div className="summary-total-note">Server recalculates &amp; verifies final total</div>
                </div>
                <div className="summary-total-amount" aria-label={`Estimated total: $${cartTotal.toFixed(2)} USD`}>
                  ${cartTotal.toFixed(2)}
                </div>
              </div>
            </>
          ) : (
            <div className="summary-empty" role="status">
              <CartIcon />
              <p>Your cart is empty.<br />Add items from the catalogue.</p>
            </div>
          )}

          <section className="checkout-address-form" aria-labelledby="delivery-heading">
            <div>
              <h3 id="delivery-heading" className="checkout-address-title">Delivery details</h3>
              <p className="checkout-address-note">These details are saved with the order and sent to PayPal for this physical-goods purchase.</p>
            </div>
            <label className="checkout-field" htmlFor="checkout-buyer-name">
              <span>Recipient full name</span>
              <input
                id="checkout-buyer-name"
                type="text"
                autoComplete="shipping name"
                maxLength={100}
                value={checkoutDetails.buyerName}
                onChange={event => setCheckoutDetails(current => ({ ...current, buyerName: event.target.value }))}
                placeholder="Name on the delivery"
                required
              />
            </label>
            <label className="checkout-field" htmlFor="checkout-address-line1">
              <span>Street address</span>
              <input
                id="checkout-address-line1"
                type="text"
                autoComplete="shipping address-line1"
                maxLength={120}
                value={checkoutDetails.addressLine1}
                onChange={event => setCheckoutDetails(current => ({ ...current, addressLine1: event.target.value }))}
                placeholder="House number and street"
                required
              />
            </label>
            <label className="checkout-field" htmlFor="checkout-address-line2">
              <span>Apartment, suite or landmark <small>(optional)</small></span>
              <input
                id="checkout-address-line2"
                type="text"
                autoComplete="shipping address-line2"
                maxLength={120}
                value={checkoutDetails.addressLine2}
                onChange={event => setCheckoutDetails(current => ({ ...current, addressLine2: event.target.value }))}
                placeholder="Apartment, unit, building"
              />
            </label>
            <div className="checkout-address-grid">
              <label className="checkout-field" htmlFor="checkout-city">
                <span>City</span>
                <input
                  id="checkout-city"
                  type="text"
                  autoComplete="shipping address-level2"
                  maxLength={120}
                  value={checkoutDetails.city}
                  onChange={event => setCheckoutDetails(current => ({ ...current, city: event.target.value }))}
                  required
                />
              </label>
              <label className="checkout-field" htmlFor="checkout-state">
                <span>
                  State / region{' '}
                  <small>{regionRequired ? '(required)' : '(optional)'}</small>
                </span>
                <input
                  id="checkout-state"
                  type="text"
                  autoComplete="shipping address-level1"
                  maxLength={120}
                  value={checkoutDetails.state}
                  onChange={event => setCheckoutDetails(current => ({ ...current, state: event.target.value }))}
                  required={regionRequired}
                />
              </label>
              <label className="checkout-field" htmlFor="checkout-postal">
                <span>Postal code</span>
                <input
                  id="checkout-postal"
                  type="text"
                  autoComplete="shipping postal-code"
                  maxLength={120}
                  value={checkoutDetails.postalCode}
                  onChange={event => setCheckoutDetails(current => ({ ...current, postalCode: event.target.value }))}
                  required
                />
              </label>
              <label className="checkout-field" htmlFor="checkout-country">
                <span>Country code</span>
                <input
                  id="checkout-country"
                  type="text"
                  autoComplete="shipping country"
                  maxLength={2}
                  minLength={2}
                  value={checkoutDetails.countryCode}
                  onChange={event => setCheckoutDetails(current => ({ ...current, countryCode: event.target.value.toUpperCase() }))}
                  placeholder="IN"
                  required
                />
              </label>
            </div>
          </section>

          {checkoutError && (
            <div className="findings-box issues summary-error" role="alert">
              {checkoutError}
            </div>
          )}

          <button
            className="btn-paypal"
            onClick={handleCheckout}
            disabled={
              !hasItems ||
              checkoutLoading ||
              !checkoutDetails.buyerName.trim() ||
              !checkoutDetails.addressLine1.trim() ||
              !checkoutDetails.city.trim() ||
              !checkoutDetails.postalCode.trim() ||
              !/^[A-Z]{2}$/.test(checkoutDetails.countryCode.trim().toUpperCase()) ||
              (regionRequired && !checkoutDetails.state.trim())
            }
            aria-label={!hasItems ? 'Add items to cart before checking out' : 'Complete delivery details before PayPal checkout'}
          >
            {checkoutLoading ? (
              <>
                <span className="btn-spinner" aria-hidden="true"></span>
                Creating order…
              </>
            ) : (
              <>
                <PayPalIcon />
                Proceed to PayPal
              </>
            )}
          </button>

          <div className="summary-security-note">
            <LockIcon />
            <span>Payments processed securely via PayPal Sandbox. No charges until you approve.</span>
          </div>
        </aside>
      </div>
    </main>
  )
}

// ─── Checkout Return View ─────────────────────────────────────────────────────
function CheckoutReturnView({ captureLoading, captureError, captureResult, navigateTo }) {
  const isPaid = captureResult?.payment_status === 'PAID' || captureResult?.already_captured

  if (captureLoading) {
    return (
      <main className="main" id="main-content">
        <header className="topbar">
          <div className="breadcrumb">
            <span>Workspace</span>
            <span>/</span>
            <span>New Checkout</span>
            <span>/</span>
            <strong>Processing Payment</strong>
          </div>
        </header>
        <div className="result-card-wrap">
          <div className="result-card" role="status" aria-live="polite" aria-label="Processing payment">
            <div className="result-card-icon processing">
              <SpinnerIcon />
            </div>
            <h1 className="result-card-heading">Processing payment…</h1>
            <p className="result-card-sub">Please wait while we confirm your payment with PayPal.</p>
          </div>
        </div>
      </main>
    )
  }

  if (captureError) {
    return (
      <main className="main" id="main-content">
        <header className="topbar">
          <div className="breadcrumb">
            <span>Workspace</span>
            <span>/</span>
            <span>New Checkout</span>
            <span>/</span>
            <strong>Payment Error</strong>
          </div>
        </header>
        <div className="result-card-wrap">
          <div className="result-card result-card--error" role="alert">
            <div className="result-card-icon error">
              <CancelCircleIcon />
            </div>
            <h1 className="result-card-heading">Payment not verified</h1>
            <p className="result-card-sub">{captureError}</p>
            <div className="result-card-actions">
              <button className="btn-primary" onClick={() => navigateTo('/checkout')}>
                Try checkout again
              </button>
              <button className="btn-secondary" onClick={() => navigateTo('/')}>
                Shipment Review
              </button>
            </div>
          </div>
        </div>
      </main>
    )
  }

  if (isPaid) {
    return (
      <main className="main" id="main-content">
        <header className="topbar">
          <div className="breadcrumb">
            <span>Workspace</span>
            <span>/</span>
            <span>New Checkout</span>
            <span>/</span>
            <strong>Payment Successful</strong>
          </div>
        </header>
        <div className="result-card-wrap">
          <div className="result-card result-card--success">
            <div className="result-card-icon success" aria-hidden="true">
              <SuccessCircleIcon />
            </div>
            <div className="result-status-badge pill pill-pass">PAID</div>
            <h1 className="result-card-heading">Payment successful</h1>
            <p className="result-card-sub">
              Your payment has been captured and confirmed by PayPal Sandbox.
            </p>

            <dl className="result-detail-list">
              <div className="result-detail-row">
                <dt>Local Order ID</dt>
                <dd className="result-detail-value">{captureResult.order_id}</dd>
              </div>
              {captureResult.buyer_name && (
                <div className="result-detail-row">
                  <dt>Recipient</dt>
                  <dd className="result-detail-value">{captureResult.buyer_name}</dd>
                </div>
              )}
              {captureResult.shipping_address && (
                <div className="result-detail-row">
                  <dt>Delivery Address</dt>
                  <dd className="result-detail-value">
                    {[
                      captureResult.shipping_address.address_line_1,
                      captureResult.shipping_address.address_line_2,
                      captureResult.shipping_address.city,
                      captureResult.shipping_address.state,
                      captureResult.shipping_address.postal_code,
                      captureResult.shipping_address.country_code
                    ].filter(Boolean).join(', ')}
                  </dd>
                </div>
              )}
              {captureResult.shipment_order_id && (
                <div className="result-detail-row">
                  <dt>Shipment ID</dt>
                  <dd className="result-detail-value">
                    <strong style={{ color: 'var(--primary, #0070ba)' }}>{captureResult.shipment_order_id}</strong>
                  </dd>
                </div>
              )}
              {captureResult.paypal_capture_id && (
                <div className="result-detail-row">
                  <dt>PayPal Capture ID</dt>
                  <dd className="result-detail-value">{captureResult.paypal_capture_id}</dd>
                </div>
              )}
              {captureResult.paypal_order_id && (
                <div className="result-detail-row">
                  <dt>PayPal Order ID</dt>
                  <dd className="result-detail-value">{captureResult.paypal_order_id}</dd>
                </div>
              )}
              <div className="result-detail-row">
                <dt>Payment Status</dt>
                <dd>
                  <span className="pill pill-pass">PAID</span>
                </dd>
              </div>
            </dl>

            {captureResult.items?.length > 0 && (
              <section className="result-order-items" aria-label="Items in this order">
                <h2>Items in this order</h2>
                <ul>
                  {captureResult.items.map(item => (
                    <li key={item.id || item.sku}>
                      <div>
                        <strong>{item.name}</strong>
                        <small>{item.sku} · Qty {item.quantity} × ${item.unit_price}</small>
                      </div>
                      <strong>${item.line_total}</strong>
                    </li>
                  ))}
                </ul>
                <div className="result-order-total">
                  <span>Total paid</span>
                  <strong>${captureResult.total} {captureResult.currency || 'USD'}</strong>
                </div>
              </section>
            )}

            <div className="result-card-actions">
              {captureResult.shipment_order_id ? (
                <button
                  className="btn-primary"
                  onClick={() => navigateTo('/manifests', { shipmentId: captureResult.shipment_order_id })}
                >
                  Review shipment manifest →
                </button>
              ) : null}
              <button className={captureResult.shipment_order_id ? 'btn-secondary' : 'btn-primary'} onClick={() => navigateTo('/')}>
                View Shipment Review
              </button>
              <button className="btn-secondary" onClick={() => navigateTo('/checkout')}>
                Create another checkout
              </button>
            </div>
          </div>
        </div>
      </main>
    )
  }

  return (
    <main className="main" id="main-content">
      <header className="topbar">
        <div className="breadcrumb">
          <span>Workspace</span>
          <span>/</span>
          <span>New Checkout</span>
          <span>/</span>
          <strong>Payment Unverified</strong>
        </div>
      </header>
      <div className="result-card-wrap">
        <div className="result-card result-card--error" role="alert">
          <div className="result-card-icon error" aria-hidden="true">
            <CancelCircleIcon />
          </div>
          <h1 className="result-card-heading">Payment not verified</h1>
          <p className="result-card-sub">
            We could not confirm a successful payment status. No funds have been taken. Please try again.
          </p>
          <div className="result-card-actions">
            <button className="btn-primary" onClick={() => navigateTo('/checkout')}>
              Try checkout again
            </button>
            <button className="btn-secondary" onClick={() => navigateTo('/')}>
              Shipment Review
            </button>
          </div>
        </div>
      </div>
    </main>
  )
}

// ─── Checkout Cancel View ─────────────────────────────────────────────────────
function CheckoutCancelView({ navigateTo }) {
  return (
    <main className="main" id="main-content">
      <header className="topbar">
        <div className="breadcrumb">
          <span>Workspace</span>
          <span>/</span>
          <span>New Checkout</span>
          <span>/</span>
          <strong>Payment Cancelled</strong>
        </div>
      </header>
      <div className="result-card-wrap">
        <div className="result-card result-card--cancel">
          <div className="result-card-icon cancel" aria-hidden="true">
            <CancelCircleIcon />
          </div>
          <div className="result-status-badge pill pill-warn">CANCELLED</div>
          <h1 className="result-card-heading">Payment not completed</h1>
          <p className="result-card-sub">
            You returned from PayPal without completing the checkout. No charges were made and your order has not been processed.
          </p>
          <div className="result-card-actions">
            <button className="btn-primary" onClick={() => navigateTo('/checkout')}>
              Return to checkout
            </button>
            <button className="btn-secondary" onClick={() => navigateTo('/')}>
              View Shipment Review
            </button>
          </div>
        </div>
      </div>
    </main>
  )
}

createRoot(document.getElementById('root')).render(<App />)
