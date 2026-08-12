'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import {
  AlertTriangle,
  ArrowLeft,
  Ban,
  Download,
  FileWarning,
  History,
  Link2,
  Loader2,
  Moon,
  ShieldCheck,
  ShieldHalf,
  Sparkles,
  Sun,
} from 'lucide-react'
import { ScoreBar } from '@/components/ScoreBar'
import { ApiError, apiGet, apiPost, getApiBaseUrl } from '@/lib/api'
import { generateRunReportPdf } from '@/lib/pdfReport'
import { useTheme } from '@/lib/theme'
import type { ReportResponse, RunDetail, VerdictLabel } from '@/lib/types'

type Severity = 'Critical' | 'High' | 'Medium' | 'Low' | 'Safe' | 'Unknown'

const verdictClass: Record<Severity, string> = {
  Critical: 'critical',
  High: 'high',
  Medium: 'medium',
  Low: 'low',
  Safe: 'safe',
  Unknown: 'unknown',
}

function severityFromLabel(label?: VerdictLabel | string): Severity {
  switch (label) {
    case 'dangerous':
      return 'Critical'
    case 'suspicious':
      return 'Medium'
    case 'safe':
      return 'Safe'
    case 'inconclusive':
      return 'Low'
    default:
      return 'Low'
  }
}

function meterColor(sev: Severity): string {
  if (sev === 'Critical' || sev === 'High') return 'var(--red)'
  if (sev === 'Medium') return 'var(--yellow)'
  if (sev === 'Safe') return 'var(--green)'
  return 'var(--muted)'
}

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : 'Something went wrong. Try again.'
}

function relativeTime(seconds: number): string {
  const diff = Date.now() - seconds * 1000
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs} hr${hrs > 1 ? 's' : ''} ago`
  const days = Math.floor(hrs / 24)
  return `${days} day${days > 1 ? 's' : ''} ago`
}

// screenshot_path is a repo-relative file path (e.g. "data/screenshots/foo.png")
// — the backend serves the file itself at GET /screenshots/<basename>
// (api/app.py), so only the basename is needed once turned into a URL.
// (The old .md report download used the equivalent /reports/<basename>
// mount — no longer needed now that the report is a client-built PDF,
// see lib/pdfReport.ts.)
function fileUrl(mount: 'screenshots', path: string): string {
  return `${getApiBaseUrl()}/${mount}/${path.split(/[/\\]/).pop()}`
}

// inspect_website's navigation_error is a raw Playwright/Python exception
// string (e.g. "Page.goto: Timeout 12000ms exceeded. Call log: ...") — a
// developer error message, not something to show someone reading a
// security report. Translate the common cases into plain language; fall
// back to a generic line rather than the raw text for anything else.
function friendlyNavError(raw?: string): string {
  if (!raw) return 'the sandbox could not load the page.'
  const text = raw.toLowerCase()
  if (text.includes('timeout')) return 'the page took too long to load and timed out.'
  if (text.includes('err_name_not_resolved') || text.includes('name_not_resolved')) {
    return "the domain doesn't resolve — it may not actually exist."
  }
  if (text.includes('err_connection_refused') || text.includes('connection refused')) {
    return 'the server refused the connection.'
  }
  if (text.includes('cert') || text.includes('ssl')) return "the site's security certificate could not be verified."
  return 'the page failed to load.'
}

// The agent's REASON is now written as an opening sentence plus "- "
// bullet points (agent/agent_node.py's system prompt asks for exactly
// that, in plain language — see the prompt for why), and may use
// **bold** for emphasis. No markdown library for this on purpose — the
// format is deliberately this narrow, so a small dedicated renderer
// covers it without a new dependency.
function renderInline(text: string): React.ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') ? <strong key={i}>{part.slice(2, -2)}</strong> : <span key={i}>{part}</span>,
  )
}

function ReasonText({ text }: { text: string }) {
  const lines = text
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
  const blocks: { type: 'p' | 'ul'; lines: string[] }[] = []
  for (const line of lines) {
    const bullet = line.startsWith('- ') || line.startsWith('* ')
    const content = bullet ? line.slice(2).trim() : line
    const last = blocks[blocks.length - 1]
    const type = bullet ? 'ul' : 'p'
    if (last?.type === type) last.lines.push(content)
    else blocks.push({ type, lines: [content] })
  }
  return (
    <div className="reason-text">
      {blocks.map((block, i) =>
        block.type === 'ul' ? (
          <ul key={i}>
            {block.lines.map((line, j) => (
              <li key={j}>{renderInline(line)}</li>
            ))}
          </ul>
        ) : (
          block.lines.map((line, j) => <p key={`${i}-${j}`}>{renderInline(line)}</p>)
        ),
      )}
    </div>
  )
}

export default function RunPage() {
  const params = useParams<{ id: string }>()
  const router = useRouter()
  const { dark, toggleTheme } = useTheme()
  const [detail, setDetail] = useState<RunDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    setDetail(null)
    setError(null)
    apiGet<RunDetail>(`/runs/${params.id}`)
      .then((d) => alive && setDetail(d))
      .catch((err) => alive && setError(errorMessage(err)))
    return () => {
      alive = false
    }
  }, [params.id])

  return (
    <div className={dark ? 'app-shell dark' : 'app-shell'} suppressHydrationWarning>
      <div className="run-page">
        <header className="run-topbar">
          <button className="icon-button" onClick={() => router.push('/')} aria-label="Back to dashboard">
            <ArrowLeft size={18} />
          </button>
          <div className="brand run-brand">
            <div className="brand-mark">
              <ShieldHalf size={18} />
            </div>
            <span>Security Copilot</span>
          </div>
          <div className="top-actions">
            <button className="icon-button" onClick={toggleTheme} aria-label="Toggle theme">
              {dark ? <Sun size={17} /> : <Moon size={17} />}
            </button>
          </div>
        </header>

        {error ? (
          <div className="run-state">
            <AlertTriangle size={20} />
            <p>{error}</p>
          </div>
        ) : !detail ? (
          <div className="run-state">
            <Loader2 className="spin" size={20} />
            <p>Loading investigation…</p>
          </div>
        ) : (
          <RunReport detail={detail} />
        )}
      </div>
    </div>
  )
}

function RunReport({ detail }: { detail: RunDetail }) {
  const sev = severityFromLabel(detail.verdict?.label)
  const score = Math.round((detail.verdict?.confidence ?? 0) * 100)
  const reason = detail.verdict?.reason || 'No reasoning was recorded for this run.'
  const mitigation = detail.verdict?.mitigation
  const alternatives = detail.verdict?.legitimate_alternatives ?? []

  const inspectCalls = detail.tool_calls.filter((c) => c.tool === 'inspect_website')
  const vtCalls = detail.tool_calls.filter((c) => c.tool === 'domain_reputation' && c.artifact.virustotal?.available)
  const recallCalls = detail.tool_calls.filter(
    (c) => c.tool === 'recall_similar_cases' && (c.artifact.matches?.length ?? 0) > 0,
  )

  return (
    <div className="run-body">
      {/* ── Summary, up top ─────────────────────────────────── */}
      <section className="panel run-summary animate-in">
        <p className="eyebrow">Investigation / {detail.id}</p>
        <h1 className="run-target">{detail.raw_input}</h1>
        <div className="modal-meta">
          <span className={`badge ${verdictClass[sev]}`}>
            <span className="badge-dot" />
            {sev}
          </span>
          <span>{relativeTime(detail.created_at)}</span>
          <DownloadReportButton detail={detail} />
          {detail.case_type === 'link' && <ReportBlockButton url={detail.raw_input} />}
        </div>
        {/* ── Visual score bar — colored by verdict classification, not the ── */}
        {/* raw number: this is confidence in the verdict, not a safety %. */}
        <div className="run-score-bar">
          <div className="run-score-bar-head">
            <strong>{score}</strong>
            <span>/ 100 risk score</span>
          </div>
          <ScoreBar score={score} color={meterColor(sev)} className="run-score-bar-track" />
        </div>
        <div className="detail-box run-reason">
          <Sparkles size={17} />
          <ReasonText text={reason} />
        </div>
        {mitigation && (
          <div className="detail-box">
            <ShieldCheck size={17} />
            <ReasonText text={mitigation} />
          </div>
        )}
        {alternatives.length > 0 && (
          <div className="alt-links">
            <p className="eyebrow">Legitimate alternatives</p>
            {alternatives.map((alt) => (
              <a key={alt.url} href={alt.url} target="_blank" rel="noreferrer">
                <Link2 size={13} />
                {alt.title}
              </a>
            ))}
          </div>
        )}
      </section>

      {/* ── What the sandbox actually saw on each page it visited ── */}
      {inspectCalls.length > 0 && (
        <section className="panel animate-in animate-in-delay-1">
          {inspectCalls.map((call, i) => (
            <PageInspection key={i} call={call} index={i} total={inspectCalls.length} />
          ))}
        </section>
      )}

      {/* ── VirusTotal, per domain checked ─────────────────────── */}
      {vtCalls.map((call, i) => (
        <VirusTotalPanel key={i} call={call} />
      ))}

      {/* ── Past investigations this one resembles ─────────────── */}
      {recallCalls.map((call, i) => (
        <SimilarCasesPanel key={i} call={call} />
      ))}

      {detail.tool_calls.length === 0 && (
        <section className="panel animate-in animate-in-delay-1">
          <p className="eyebrow">Investigation steps</p>
          <p className="muted">
            This verdict was served from the router&apos;s fast path (a static blocklist match, or a cached result from
            an earlier check of this exact target) — no fresh tool calls ran for this specific entry.
          </p>
        </section>
      )}
    </div>
  )
}

// Builds a polished PDF client-side from the same `detail` already loaded
// for this page (see lib/pdfReport.ts) — replaces the old link straight to
// the backend's raw .md file, which wasn't something you'd want to hand
// to someone outside the team.
function DownloadReportButton({ detail }: { detail: RunDetail }) {
  const [busy, setBusy] = useState(false)

  async function handleClick() {
    setBusy(true)
    try {
      await generateRunReportPdf(detail)
    } finally {
      setBusy(false)
    }
  }

  return (
    <button className="button secondary run-download" onClick={handleClick} disabled={busy}>
      {busy ? <Loader2 size={14} className="spin" /> : <Download size={14} />}
      {busy ? 'Preparing PDF…' : 'Download report'}
    </button>
  )
}

// Reports outward instead of attacking the target directly (see
// backend/reporting.py's module docstring for why: hacking back is
// illegal even against confirmed criminals, and a request flood is a DoS
// attack regardless of intent). Two independent, best-effort actions —
// this tool's own blocklist (which takes effect immediately: the router
// checks it before anything else, so a re-check of this exact URL right
// after clicking this comes back "dangerous" with no agent run at all)
// and a VirusTotal submission + malicious vote, contributing to the real
// takedown/reputation pipeline other tools and browsers already consult.
function ReportBlockButton({ url }: { url: string }) {
  const [state, setState] = useState<
    { status: 'idle' } | { status: 'loading' } | { status: 'done'; result: ReportResponse } | { status: 'error'; message: string }
  >({ status: 'idle' })

  async function handleClick() {
    setState({ status: 'loading' })
    try {
      const result = await apiPost<ReportResponse>('/report', { url })
      setState({ status: 'done', result })
    } catch (err) {
      setState({ status: 'error', message: errorMessage(err) })
    }
  }

  if (state.status === 'done') {
    const { result } = state
    return (
      <span className="report-block-done">
        <Ban size={14} />
        {result.added_to_blocklist ? 'Blocked' : 'Already blocked'}
        {result.virustotal.reported ? ' & reported to VirusTotal.' : ` — VirusTotal report: ${result.virustotal.detail}`}
      </span>
    )
  }

  return (
    <button className="button secondary run-report-block" onClick={handleClick} disabled={state.status === 'loading'}>
      {state.status === 'loading' ? <Loader2 size={14} className="spin" /> : <Ban size={14} />}
      {state.status === 'loading' ? 'Reporting…' : 'Report & block'}
      {state.status === 'error' && <span className="report-block-error"> — {state.message}</span>}
    </button>
  )
}

function PageInspection({
  call,
  index,
  total,
}: {
  call: RunDetail['tool_calls'][number]
  index: number
  total: number
}) {
  const a = call.artifact
  const crossOriginLinks = (a.links ?? []).filter((l) => !l.same_origin).length
  const passwordForms = (a.forms ?? []).filter((f) => f.has_password_field)
  const visitedUrl = typeof call.args.url === 'string' ? call.args.url : undefined
  // Only worth showing when the browser actually hopped through more than
  // one URL to get there (a redirect chain of exactly the target URL
  // itself, with nothing before it, isn't a "redirect" worth reporting).
  const hops = a.redirect_chain ?? []

  return (
    <>
      <div className="inspection-heading">
        <p className="eyebrow">
          {total > 1 ? `Page ${index + 1} of ${total} — what the sandbox found` : 'What the sandbox found on the page'}
        </p>
      </div>
      {visitedUrl && total > 1 && <p className="muted">{visitedUrl}</p>}
      {hops.length > 1 && (
        <ul className="redirect-chain">
          {hops.map((hop, i) => (
            <li key={i}>
              {i > 0 && '→'}
              <span>{hop.url}</span>
              {typeof hop.status === 'number' && <span className="status">{hop.status}</span>}
            </li>
          ))}
        </ul>
      )}
      {call.screenshot_path ? (
        <div className="screenshot-block">
          <img src={fileUrl('screenshots', call.screenshot_path)} alt="Sandbox screenshot of the scanned page" loading="lazy" />
        </div>
      ) : (
        <div className="detail-box run-no-screenshot">
          <FileWarning size={17} />
          <p>No screenshot was captured — {friendlyNavError(a.navigation_error || a.error)}</p>
        </div>
      )}
      <ul className="inspection-facts">
        {a.final_url && <li>Landed on: {a.final_url}</li>}
        {typeof a.status_code === 'number' && <li>Server responded with HTTP {a.status_code}</li>}
        {a.forms && (
          <li>
            {a.forms.length === 0
              ? 'No forms on the page.'
              : `${a.forms.length} form${a.forms.length > 1 ? 's' : ''} found${
                  passwordForms.length > 0
                    ? `, ${passwordForms.length} asking for a password (submits to: ${passwordForms
                        .map((f) => f.action || 'the current page')
                        .join(', ')})`
                    : ' — none ask for a password'
                }.`}
          </li>
        )}
        {a.links && (
          <li>
            {a.links.length} outbound link{a.links.length === 1 ? '' : 's'} found
            {crossOriginLinks > 0 ? `, ${crossOriginLinks} pointing to a different domain.` : '.'}
          </li>
        )}
        {a.network_requests && <li>{a.network_requests.length} network requests while loading.</li>}
        {a.asset_dominant_foreign_origin && (
          <li>
            {a.asset_dominant_foreign_origin.asset_count} of this page&apos;s images/scripts/stylesheets load directly
            from <strong>{a.asset_dominant_foreign_origin.domain}</strong>, not the page&apos;s own domain — a common
            sign of a copied page reusing the real site&apos;s assets.
          </li>
        )}
        {a.server_ip && <li>Served from IP address {a.server_ip}.</li>}
      </ul>
      {a.page_text && (
        <>
          <p className="eyebrow run-subhead">Visible page text (excerpt)</p>
          <pre className="page-text-excerpt">{a.page_text.slice(0, 800)}</pre>
        </>
      )}
    </>
  )
}

function VirusTotalPanel({ call }: { call: RunDetail['tool_calls'][number] }) {
  const vt = call.artifact.virustotal!
  const whois = call.artifact.whois
  const domain = typeof call.artifact.domain === 'string' ? call.artifact.domain : undefined
  const malicious = vt.malicious_count ?? 0
  const suspicious = vt.suspicious_count ?? 0
  const harmless = vt.harmless_count ?? 0
  const vtTotal = malicious + suspicious + harmless

  return (
    <section className="panel vt-block animate-in animate-in-delay-2">
      <p className="eyebrow">VirusTotal{domain ? ` · ${domain}` : ''}</p>
      <p className="muted">
        {malicious + suspicious === 0
          ? `No security vendors currently flag this domain as bad${harmless > 0 ? `, and ${harmless} actively vouch it's harmless.` : '.'}`
          : `${malicious + suspicious} of the security vendors VirusTotal checks with flag this domain as ${
              malicious > 0 ? 'malicious' : 'suspicious'
            }${harmless > 0 ? `, while ${harmless} call it harmless` : ''}.`}
      </p>
      {/* ── Visual proportion bar ──────────────────────────────── */}
      {vtTotal > 0 && (
        <div className="vt-proportion-bar">
          {malicious > 0 && (
            <span
              className="vt-proportion-seg malicious"
              style={{ width: `${(malicious / vtTotal) * 100}%` }}
            />
          )}
          {suspicious > 0 && (
            <span
              className="vt-proportion-seg suspicious"
              style={{ width: `${(suspicious / vtTotal) * 100}%` }}
            />
          )}
          {harmless > 0 && (
            <span
              className="vt-proportion-seg harmless"
              style={{ width: `${(harmless / vtTotal) * 100}%` }}
            />
          )}
        </div>
      )}
      <div className="vt-counts">
        <span className="vt-count malicious">{malicious} malicious</span>
        <span className="vt-count suspicious">{suspicious} suspicious</span>
        <span className="vt-count harmless">{harmless} harmless</span>
        {typeof vt.community_reputation === 'number' && (
          <span className="vt-count">community rep {vt.community_reputation}</span>
        )}
      </div>
      {vt.flagged_by && vt.flagged_by.length > 0 && (
        <>
          <p className="eyebrow run-subhead">Vendors flagging it, and what they called it</p>
          <ul className="vt-vendors">
            {vt.flagged_by.map((f) => (
              <li key={f.vendor}>
                <strong>{f.vendor}</strong>
                {f.category ? ` · ${f.category}` : ''}
                {f.result ? ` — ${f.result}` : ''}
              </li>
            ))}
          </ul>
        </>
      )}
      {vt.categories && Object.keys(vt.categories).length > 0 && (
        <p className="vt-categories">
          {Object.entries(vt.categories)
            .map(([vendor, label]) => `${vendor}: ${label}`)
            .join(' · ')}
        </p>
      )}
      {whois?.available && whois.detail && <p className="vt-whois">{whois.detail}</p>}
    </section>
  )
}

// The agent's recall_similar_cases tool (backend/memory/case_index.py) —
// past investigations that resemble this one in substance, surfaced as
// corroborating context rather than a verdict on their own (a strong match
// raises confidence, it never single-handedly proves anything — see the
// system prompt's guidance on this tool).
function SimilarCasesPanel({ call }: { call: RunDetail['tool_calls'][number] }) {
  const router = useRouter()
  const matches = call.artifact.matches ?? []

  return (
    <section className="panel vt-block similar-cases-block animate-in animate-in-delay-3">
      <p className="eyebrow case-match-eyebrow">
        <History size={12} />
        Similar past investigations
      </p>
      <ul className="case-match-list">
        {matches.map((m) => {
          const sev = severityFromLabel(m.label)
          return (
            <li key={m.run_id} className="case-match" onClick={() => router.push(`/run/${m.run_id}`)}>
              <div className="case-match-head">
                <span className={`badge ${verdictClass[sev]}`}>
                  <span className="badge-dot" />
                  {sev}
                </span>
                <span className="case-match-target">{m.raw_input}</span>
                <span className="case-match-sim">{Math.round(m.similarity * 100)}% similar</span>
              </div>
              <p className="muted case-match-reason">{m.reason.slice(0, 220)}</p>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
