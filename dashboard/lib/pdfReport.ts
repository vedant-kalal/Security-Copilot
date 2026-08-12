/**
 * Client-side PDF export for a run's investigation report — replaces the
 * old "download the raw .md file" link. Built entirely from the same
 * `RunDetail` the run page already has in memory (no new backend
 * endpoint needed), using jsPDF directly rather than html2canvas-style
 * DOM screenshotting: this app's dark theme + CSS custom properties
 * don't reliably rasterize, and a hand-laid-out PDF prints cleanly in
 * any viewer regardless of which theme the dashboard happened to be in.
 */
import { jsPDF } from 'jspdf'
import { getApiBaseUrl } from '@/lib/api'
import type { RunDetail, VerdictLabel } from '@/lib/types'

type RGB = [number, number, number]

const COLOR = {
  critical: [220, 38, 38] as RGB,
  medium: [217, 119, 6] as RGB,
  low: [37, 99, 235] as RGB,
  safe: [22, 163, 74] as RGB,
  fg: [15, 23, 42] as RGB,
  muted: [100, 116, 139] as RGB,
  line: [226, 232, 240] as RGB,
  soft: [241, 245, 249] as RGB,
  white: [255, 255, 255] as RGB,
}

function severityColor(label?: VerdictLabel | string): RGB {
  switch (label) {
    case 'dangerous':
      return COLOR.critical
    case 'suspicious':
      return COLOR.medium
    case 'safe':
      return COLOR.safe
    default:
      return COLOR.low
  }
}

function severityLabel(label?: VerdictLabel | string): string {
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
      return 'Unknown'
  }
}

// Strips the "**bold**" markers agent_node.py's REASON format uses —
// plain text is a reasonable tradeoff here rather than laying out mixed
// bold/regular runs per line for a one-off export.
function plain(text: string): string {
  return text.replace(/\*\*([^*]+)\*\*/g, '$1')
}

function reasonBullets(text: string): { heading: string[]; bullets: string[] } {
  const lines = plain(text)
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
  const heading: string[] = []
  const bullets: string[] = []
  for (const line of lines) {
    if (line.startsWith('- ') || line.startsWith('* ')) bullets.push(line.slice(2).trim())
    else heading.push(line)
  }
  return { heading, bullets }
}

async function fetchImageAsDataUrl(url: string): Promise<{ dataUrl: string; width: number; height: number } | null> {
  try {
    // no-store, deliberately: the run page already loaded this exact URL
    // via a plain <img src>, which the browser caches as an opaque
    // no-cors response. Reusing that cache entry for this fetch() (a
    // CORS-mode request) fails with a generic "Failed to fetch" even
    // though the resource and its CORS headers are both fine — confirmed
    // by the fact that a fresh request for the same URL succeeds.
    const resp = await fetch(url, { cache: 'no-store' })
    if (!resp.ok) return null
    const blob = await resp.blob()
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result as string)
      reader.onerror = () => reject(new Error('read failed'))
      reader.readAsDataURL(blob)
    })
    const dims = await new Promise<{ width: number; height: number }>((resolve, reject) => {
      const img = new window.Image()
      img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight })
      img.onerror = () => reject(new Error('decode failed'))
      img.src = dataUrl
    })
    return { dataUrl, ...dims }
  } catch {
    return null
  }
}

const MARGIN = 18
const PAGE_W = 210
const PAGE_H = 297
const CONTENT_W = PAGE_W - MARGIN * 2
const FOOTER_Y = PAGE_H - 12

class Layout {
  doc: jsPDF
  y = MARGIN

  constructor(doc: jsPDF) {
    this.doc = doc
  }

  ensureSpace(h: number) {
    if (this.y + h > FOOTER_Y - 4) {
      this.doc.addPage()
      this.y = MARGIN
    }
  }

  heading(text: string) {
    this.ensureSpace(12)
    this.doc.setFont('helvetica', 'bold')
    this.doc.setFontSize(10.5)
    this.doc.setTextColor(...COLOR.fg)
    this.doc.text(text.toUpperCase(), MARGIN, this.y)
    this.y += 2
    this.doc.setDrawColor(...COLOR.line)
    this.doc.setLineWidth(0.3)
    this.doc.line(MARGIN, this.y, MARGIN + CONTENT_W, this.y)
    this.y += 6
  }

  paragraph(text: string, opts?: { size?: number; color?: RGB; bold?: boolean }) {
    const size = opts?.size ?? 9.5
    const color = opts?.color ?? COLOR.fg
    this.doc.setFont('helvetica', opts?.bold ? 'bold' : 'normal')
    this.doc.setFontSize(size)
    this.doc.setTextColor(...color)
    const lines: string[] = this.doc.splitTextToSize(text, CONTENT_W)
    const lineH = size * 0.42
    for (const line of lines) {
      this.ensureSpace(lineH)
      this.doc.text(line, MARGIN, this.y)
      this.y += lineH
    }
  }

  bullet(text: string) {
    this.doc.setFont('helvetica', 'normal')
    this.doc.setFontSize(9.5)
    this.doc.setTextColor(...COLOR.fg)
    const lines: string[] = this.doc.splitTextToSize(text, CONTENT_W - 6)
    lines.forEach((line: string, i: number) => {
      this.ensureSpace(5)
      if (i === 0) {
        this.doc.setFillColor(...COLOR.muted)
        this.doc.circle(MARGIN + 1, this.y - 1.4, 0.6, 'F')
      }
      this.doc.text(line, MARGIN + 5, this.y)
      this.y += 5
    })
    this.y += 1.5
  }

  spacer(h = 6) {
    this.y += h
  }
}

export async function generateRunReportPdf(detail: RunDetail): Promise<void> {
  const doc = new jsPDF({ unit: 'mm', format: 'a4' })
  const verdict = detail.verdict ?? {}
  const sev = severityColor(verdict.label)
  const sevText = severityLabel(verdict.label)
  const score = Math.round((verdict.confidence ?? 0) * 100)

  // ── Header band ──────────────────────────────────────────────────
  doc.setFillColor(...COLOR.fg)
  doc.rect(0, 0, PAGE_W, 30, 'F')
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(15)
  doc.setTextColor(...COLOR.white)
  doc.text('Security Copilot', MARGIN, 14)
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(9.5)
  doc.setTextColor(...COLOR.soft)
  doc.text('Investigation Report', MARGIN, 21)

  doc.setFontSize(8)
  doc.setTextColor(...COLOR.soft)
  const generatedAt = new Date().toLocaleString()
  doc.text(`Run ${detail.id}`, PAGE_W - MARGIN, 12, { align: 'right' })
  doc.text(generatedAt, PAGE_W - MARGIN, 17, { align: 'right' })

  const layout = new Layout(doc)
  layout.y = 40

  // ── Target + verdict ─────────────────────────────────────────────
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(13)
  doc.setTextColor(...COLOR.fg)
  const targetLines: string[] = doc.splitTextToSize(detail.raw_input, CONTENT_W)
  targetLines.forEach((line: string) => {
    layout.ensureSpace(7)
    doc.text(line, MARGIN, layout.y)
    layout.y += 7
  })
  layout.spacer(2)

  // Verdict badge
  doc.setFillColor(...sev)
  const badgeW = doc.getTextWidth(sevText.toUpperCase()) + 10
  doc.roundedRect(MARGIN, layout.y - 4.5, badgeW, 6.5, 1.5, 1.5, 'F')
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(8.5)
  doc.setTextColor(...COLOR.white)
  doc.text(sevText.toUpperCase(), MARGIN + badgeW / 2, layout.y, { align: 'center' })
  layout.spacer(10)

  // Score bar — colored by classification, matching the dashboard's own
  // fix for the same "score isn't a safety percentage" issue.
  doc.setFont('helvetica', 'bold')
  doc.setFontSize(18)
  doc.setTextColor(...COLOR.fg)
  doc.text(String(score), MARGIN, layout.y)
  const scoreW = doc.getTextWidth(String(score))
  doc.setFont('helvetica', 'normal')
  doc.setFontSize(8.5)
  doc.setTextColor(...COLOR.muted)
  doc.text('/ 100 risk score', MARGIN + scoreW + 3, layout.y)
  layout.spacer(4)
  doc.setFillColor(...COLOR.soft)
  doc.roundedRect(MARGIN, layout.y, CONTENT_W, 2.5, 1, 1, 'F')
  doc.setFillColor(...sev)
  doc.roundedRect(MARGIN, layout.y, Math.max(2, (CONTENT_W * score) / 100), 2.5, 1, 1, 'F')
  layout.spacer(12)

  // ── Findings ──────────────────────────────────────────────────────
  if (verdict.reason) {
    layout.heading('Findings')
    const { heading, bullets } = reasonBullets(verdict.reason)
    heading.forEach((h) => layout.paragraph(h, { size: 10 }))
    if (heading.length) layout.spacer(2)
    bullets.forEach((b) => layout.bullet(b))
    layout.spacer(4)
  }

  if (verdict.mitigation) {
    layout.heading('Recommended action')
    layout.paragraph(plain(verdict.mitigation))
    layout.spacer(4)
  }

  const alternatives = verdict.legitimate_alternatives ?? []
  if (alternatives.length > 0) {
    layout.heading('Legitimate alternatives')
    alternatives.forEach((alt) => layout.bullet(`${alt.title} — ${alt.url}`))
    layout.spacer(4)
  }

  // ── Page inspection ───────────────────────────────────────────────
  const inspectCalls = detail.tool_calls.filter((c) => c.tool === 'inspect_website')
  for (const [i, call] of inspectCalls.entries()) {
    const a = call.artifact
    layout.heading(inspectCalls.length > 1 ? `Page inspected (${i + 1} of ${inspectCalls.length})` : 'Page inspected')
    const facts: string[] = []
    if (a.final_url) facts.push(`Landed on: ${a.final_url}`)
    if (typeof a.status_code === 'number') facts.push(`Server responded with HTTP ${a.status_code}`)
    if (a.forms) {
      const pwForms = a.forms.filter((f) => f.has_password_field)
      facts.push(
        a.forms.length === 0
          ? 'No forms on the page.'
          : `${a.forms.length} form(s) found${pwForms.length > 0 ? `, ${pwForms.length} asking for a password` : ' — none ask for a password'}.`,
      )
    }
    if (a.links) {
      const cross = a.links.filter((l) => !l.same_origin).length
      facts.push(`${a.links.length} outbound link(s) found${cross > 0 ? `, ${cross} pointing to a different domain` : ''}.`)
    }
    if (a.asset_dominant_foreign_origin) {
      facts.push(
        `${a.asset_dominant_foreign_origin.asset_count} of this page's images/scripts/stylesheets load directly from ${a.asset_dominant_foreign_origin.domain}, not the page's own domain.`,
      )
    }
    if (a.server_ip) facts.push(`Served from IP address ${a.server_ip}.`)
    facts.forEach((f) => layout.bullet(f))
    layout.spacer(2)

    if (call.screenshot_path) {
      const url = `${getApiBaseUrl()}/screenshots/${call.screenshot_path.split(/[/\\]/).pop()}`
      const img = await fetchImageAsDataUrl(url)
      if (img) {
        const w = CONTENT_W
        const h = (img.height / img.width) * w
        layout.ensureSpace(Math.min(h, PAGE_H - MARGIN * 2) + 4)
        const drawH = Math.min(h, PAGE_H - MARGIN * 2 - layout.y)
        const drawW = (drawH / h) * w
        doc.setDrawColor(...COLOR.line)
        doc.addImage(img.dataUrl, 'PNG', MARGIN, layout.y, drawW, drawH)
        doc.rect(MARGIN, layout.y, drawW, drawH)
        layout.y += drawH + 6
      }
    }
  }

  // ── VirusTotal ────────────────────────────────────────────────────
  const vtCall = detail.tool_calls.find((c) => c.tool === 'domain_reputation' && c.artifact.virustotal?.available)
  if (vtCall) {
    const vt = vtCall.artifact.virustotal!
    const domain = typeof vtCall.artifact.domain === 'string' ? vtCall.artifact.domain : undefined
    layout.heading(domain ? `VirusTotal — ${domain}` : 'VirusTotal')
    const malicious = vt.malicious_count ?? 0
    const suspicious = vt.suspicious_count ?? 0
    const harmless = vt.harmless_count ?? 0
    layout.paragraph(`${malicious} malicious · ${suspicious} suspicious · ${harmless} harmless`, { bold: true, size: 10 })
    layout.spacer(2)
    if (vt.flagged_by && vt.flagged_by.length > 0) {
      vt.flagged_by
        .slice(0, 10)
        .forEach((f) => layout.bullet(`${f.vendor}${f.category ? ` · ${f.category}` : ''}${f.result ? ` — ${f.result}` : ''}`))
    }
    layout.spacer(4)
  }

  // ── Similar past investigations ──────────────────────────────────
  const recallCall = detail.tool_calls.find((c) => c.tool === 'recall_similar_cases' && (c.artifact.matches?.length ?? 0) > 0)
  if (recallCall) {
    layout.heading('Similar past investigations')
    ;(recallCall.artifact.matches ?? []).forEach((m) => {
      layout.bullet(`${Math.round(m.similarity * 100)}% similar — ${severityLabel(m.label)} — ${m.raw_input}`)
    })
    layout.spacer(4)
  }

  // ── Footer on every page ─────────────────────────────────────────
  const pageCount = doc.getNumberOfPages()
  for (let p = 1; p <= pageCount; p++) {
    doc.setPage(p)
    doc.setDrawColor(...COLOR.line)
    doc.setLineWidth(0.2)
    doc.line(MARGIN, FOOTER_Y - 4, PAGE_W - MARGIN, FOOTER_Y - 4)
    doc.setFont('helvetica', 'normal')
    doc.setFontSize(7.5)
    doc.setTextColor(...COLOR.muted)
    doc.text('Generated by Security Copilot — automated analysis, not a substitute for human judgment.', MARGIN, FOOTER_Y)
    doc.text(`Page ${p} of ${pageCount}`, PAGE_W - MARGIN, FOOTER_Y, { align: 'right' })
  }

  const filenameBase = detail.raw_input.replace(/^https?:\/\//, '').replace(/[^a-z0-9]+/gi, '-').slice(0, 60)
  doc.save(`security-copilot-${filenameBase || detail.id}.pdf`)
}
