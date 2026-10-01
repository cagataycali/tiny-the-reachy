// Runtime settings — Voice / Agent / Telegram / Personas, generated from tools/config.py SCHEMA via GET /api/config.
// Values: config DB over .env over code default; "env" resets one key. Voice keys restart the live session by themselves.
import { useEffect, useMemo, useRef, useState } from 'react'
import { ConfigKey, ConfigSnapshot, Personas, PersonaUnit, Preview, api } from '../lib/api'

type Values = Record<string, unknown>
const GROUPS: { id: 'voice' | 'agent' | 'telegram'; title: string; blurb: string }[] = [
  { id: 'voice', title: 'voice', blurb: 'Realtime model of the voice persona. Apply ends the live session; it is back in about 10 s.' },
  { id: 'agent', title: 'agent', blurb: 'Model, personality note and tools per persona. Telegram and thinker pick changes up on their next turn.' },
  { id: 'telegram', title: 'telegram', blurb: 'Where TINY writes and who it listens to. The bot token stays in .env.' },
]

function same(a: unknown, b: unknown): boolean { return JSON.stringify(a ?? null) === JSON.stringify(b ?? null) }
function fmt(v: unknown): string { if (v == null || v === '') return 'empty'; if (Array.isArray(v)) return v.length ? v.join(', ') : 'empty'; return String(v) }
function since(u: { since: string | null; since_t: number | null }, now: number): string {
  if (u.since_t == null) return u.since ? u.since.replace(/^[A-Za-z]{3} /, '') : '--'
  const s = Math.max(0, Math.round(now - u.since_t)); const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60)
  return h ? `${h}h${m.toString().padStart(2, '0')} ago` : m ? `${m}m ago` : `${s}s ago`
}

/** One schema-driven control. `id` ties the label to the input for screen readers. */
function Field({ k, value, env, overridden, can, onChange, onReset }: {
  k: ConfigKey; value: unknown; env: unknown; overridden: boolean; can: boolean; onChange: (v: unknown) => void; onReset: () => void
}) {
  const id = `cfg-${k.key.replace(/\./g, '-')}`
  const hint = `${k.help}${k.restart === 'voice' ? ' Restarts the voice session.' : ''}`
  let control: JSX.Element
  if (k.type === 'choice') {
    control = <select id={id} className="mono" value={String(value ?? '')} disabled={!can} onChange={(e) => onChange(e.target.value)} aria-describedby={`${id}-h`}>{k.choices.map((c) => <option key={c} value={c}>{c}</option>)}</select>
  } else if (k.type === 'bool') {
    control = (
      <label className="switch" htmlFor={id}><input id={id} type="checkbox" checked={!!value} disabled={!can} onChange={(e) => onChange(e.target.checked)} aria-describedby={`${id}-h`} /><span className="track" /> <span className="mono small">{value ? 'on' : 'off'}</span></label>
    )
  } else if (k.type === 'int' || k.type === 'float') {
    control = <input id={id} className="mono" type="number" inputMode="decimal" step={k.type === 'int' ? 1 : 0.05} min={k.min ?? undefined} max={k.max ?? undefined} value={value == null ? '' : String(value)} disabled={!can} onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))} aria-describedby={`${id}-h`} />
  } else if (k.type === 'text' || k.type === 'list') {
    const txt = Array.isArray(value) ? value.join('\n') : String(value ?? '')
    control = (
      <>
        <textarea id={id} className="mono" rows={k.type === 'list' ? 3 : 4} value={txt} disabled={!can} placeholder={k.type === 'list' ? 'one per line' : ''} onChange={(e) => onChange(k.type === 'list' ? e.target.value.split('\n').map((x) => x.trim()).filter(Boolean) : e.target.value)} aria-describedby={`${id}-h`} />
        {k.type === 'text' && <span className="muted small mono cfg-count">{txt.length} chars{txt.startsWith('FULL:') ? ' · FULL: replaces the whole prompt' : ''}</span>}
      </>
    )
  } else {
    control = <input id={id} className="mono" type="text" value={String(value ?? '')} disabled={!can} onChange={(e) => onChange(e.target.value)} aria-describedby={`${id}-h`} />
  }
  return (
    <div className={`cfg-field ${overridden ? 'overridden' : ''} ${k.key === 'agent.model_id' || k.type === 'text' || k.type === 'list' ? 'wide' : ''}`} data-key={k.key}>
      <div className="cfg-label"><label htmlFor={id} className="mono">{k.label}</label>
        {overridden && <button type="button" className="btn small ghost" disabled={!can} onClick={onReset} title={`back to .env: ${fmt(env)}`} aria-label={`reset ${k.label} to env`}>env</button>}
      </div>
      {control}
      <div id={`${id}-h`} className="muted small cfg-help">{hint}</div>
    </div>
  )
}

/** Tool checklist for one persona, grouped like tools/__init__.py; dangerous tools carry an amber note. */
function ToolPicker({ persona, snap, value, can, onChange }: { persona: string; snap: ConfigSnapshot; value: string[] | null; can: boolean; onChange: (v: string[] | null) => void }) {
  const chosen = new Set(value ?? snap.defaults[persona] ?? [])
  const groups = useMemo(() => { const g: Record<string, typeof snap.catalog> = {}; for (const t of snap.catalog) (g[t.group] ||= []).push(t); return g }, [snap.catalog])
  const toggle = (name: string, on: boolean) => { const next = new Set(chosen); on ? next.add(name) : next.delete(name); onChange([...snap.catalog.map((t) => t.name).filter((n) => next.has(n))]) }
  const dangerousOn = snap.catalog.filter((t) => t.dangerous && chosen.has(t.name)).map((t) => t.name)
  return (
    <fieldset className="cfg-tools" data-testid={`tools-${persona}`}>
      <legend className="mono small">tools for <b>{persona}</b> · {chosen.size} of {snap.catalog.length}{value ? '' : ' (code default)'}
        {value && <button type="button" className="btn small ghost" disabled={!can} onClick={() => onChange(null)}>code default</button>}
      </legend>
      {Object.entries(groups).map(([g, tools]) => (
        <div key={g} className="cfg-toolgroup"><span className="muted small mono">{g}</span>
          <div className="cfg-toolgrid">
            {tools.map((t) => (
              <label key={t.name} className={`cfg-tool ${t.dangerous ? 'danger' : ''}`}>
                <input type="checkbox" checked={chosen.has(t.name)} disabled={!can} onChange={(e) => toggle(t.name, e.target.checked)} />
                <span className="mono small">{t.name}</span>
              </label>
            ))}
          </div>
        </div>
      ))}
      {dangerousOn.length > 0 && <div className="cfg-warn small" role="note">runs code or spawns agents: {dangerousOn.join(', ')}. Keep them off for personas strangers can talk to.</div>}
    </fieldset>
  )
}

export function ConfigPanel({ can, onToast }: { can: boolean; onToast: (m: string) => void }) {
  const [snap, setSnap] = useState<ConfigSnapshot | null>(null)
  const [err, setErr] = useState<string>('')
  const [draft, setDraft] = useState<Values>({})
  const [busy, setBusy] = useState<string>('')
  const [result, setResult] = useState<Record<string, string>>({})
  const [persona, setPersona] = useState('voice')
  const [preview, setPreview] = useState<Preview | null>(null)
  const [units, setUnits] = useState<Personas | null>(null)
  const timer = useRef<number | null>(null)

  const load = async () => {
    try { setSnap(await api.config()); setErr('') } catch (e: any) { setErr(e.message || 'config unavailable') }
    try { setUnits(await api.personas()) } catch { setUnits(null) }
  }
  useEffect(() => { load(); timer.current = window.setInterval(async () => { try { setUnits(await api.personas()) } catch { /* keep the last */ } }, 15000); return () => { if (timer.current) window.clearInterval(timer.current) } }, [])

  if (err && !snap) return <div className="muted small" role="status">settings: {err}</div>
  if (!snap) return <div className="muted small" role="status">loading settings</div>

  const byGroup = (g: string) => snap.schema.filter((k) => k.group === g && !k.key.startsWith('agent.tools.') && !k.key.startsWith('agent.prompt_note.'))
  const val = (key: string) => (key in draft ? draft[key] : snap.values[key])
  const dirtyKeys = (keys: string[]) => keys.filter((k) => k in draft && !same(draft[k], snap.values[k]))
  const set = (key: string, v: unknown) => setDraft((d) => ({ ...d, [key]: v }))
  const groupKeys = (g: string) => snap.schema.filter((k) => k.group === g).map((k) => k.key)

  const save = async (g: string) => {
    const keys = dirtyKeys(groupKeys(g)); if (!keys.length) return
    const body: Values = {}; for (const k of keys) body[k] = draft[k]
    setBusy(g)
    try {
      const r = await api.putConfig(body)
      setSnap((s) => (s ? { ...s, values: r.values, overrides: r.overrides, generations: r.generations } : s))
      setDraft((d) => { const n = { ...d }; for (const k of keys) delete n[k]; return n })
      const n = Object.keys(r.changed).length
      const msg = n === 0 ? 'nothing changed' : `saved ${n} ${n === 1 ? 'key' : 'keys'}${r.restart.includes('voice') ? ' · voice session restarting (~10 s)' : ''}${r.restart.includes('agent') ? ' · thinker rebuilds next cycle' : ''}`
      setResult((x) => ({ ...x, [g]: msg })); onToast(msg)
      if (persona) refreshPreview(persona)
      load()
    } catch (e: any) { setResult((x) => ({ ...x, [g]: `not saved: ${e.message}` })) } finally { setBusy('') }
  }
  const reset = async (key: string) => {
    setBusy(key)
    try { const r = await api.resetConfig(key); setSnap((s) => (s ? { ...s, values: r.values, overrides: r.overrides, generations: r.generations } : s)); setDraft((d) => { const n = { ...d }; delete n[key]; return n }); onToast(`${key} back to env`) } catch (e: any) { onToast(e.message) } finally { setBusy('') }
  }
  const refreshPreview = async (p: string) => { try { setPreview(await api.preview(p)) } catch (e: any) { setPreview(null); onToast(e.message) } }
  const restart = async (u: PersonaUnit) => {
    if (!confirm(`Restart ${u.unit}? ${u.unit === 'tiny-voice' ? 'TINY goes quiet for ~15 s.' : 'In-flight work is lost.'}`)) return
    setBusy(u.unit)
    try { await api.restartPersona(u.unit); onToast(`${u.unit} restarted`); setTimeout(load, 3000) } catch (e: any) { onToast(e.message) } finally { setBusy('') }
  }

  const voiceUnit = units?.units.find((u) => u.unit === 'tiny-voice')
  const noteKey = `agent.prompt_note.${persona}`
  const toolsKey = `agent.tools.${persona}`
  const hasNote = snap.prompt_personas.includes(persona)
  const hasTools = snap.personas.includes(persona)
  const personaChoices = Array.from(new Set([...snap.personas, ...snap.prompt_personas]))

  // a plain render helper, NOT a nested component: a component type created per render remounts its button on every
  // WS tick (10 Hz) and a click lands on a detached node (caught by the Playwright dogfood run)
  const saveRow = (g: string, label?: string) => {
    const n = dirtyKeys(groupKeys(g)).length
    return (
      <div className="cfg-actions">
        <button type="button" className="btn primary" disabled={!can || busy !== '' || n === 0} onClick={() => save(g)} data-testid={`save-${g}`}>{label ?? 'save'}{n ? ` (${n})` : ''}</button>
        {n > 0 && <button type="button" className="btn ghost" disabled={busy !== ''} onClick={() => setDraft((d) => { const x = { ...d }; for (const k of groupKeys(g)) delete x[k]; return x })}>discard</button>}
        <span className="muted small" role="status" aria-live="polite">{result[g] ?? (n ? 'unsaved changes' : '')}</span>
      </div>
    )
  }

  return (
    <div className="cfg" data-testid="config-panel">
      {GROUPS.map((g) => (
        <section key={g.id} className="cfg-section" aria-labelledby={`cfg-${g.id}-title`}>
          <h3 id={`cfg-${g.id}-title`} className="dock-sub">{g.title}</h3>
          <p className="muted small cfg-blurb">{g.blurb}</p>
          {g.id === 'voice' && voiceUnit && (
            <div className="cfg-status mono small" data-testid="voice-status">
              <span className={`dot ${voiceUnit.active === 'active' ? 'on' : ''}`} /> tiny-voice {voiceUnit.active}{voiceUnit.since ? ` · up ${since(voiceUnit, units!.t)}` : ''} · generation {snap.generations.voice}
              {voiceUnit.journal.length > 0 && <div className="muted cfg-journal">{voiceUnit.journal[voiceUnit.journal.length - 1]}</div>}
            </div>
          )}
          <div className="cfg-grid">
            {byGroup(g.id).map((k) => <Field key={k.key} k={k} value={val(k.key)} env={snap.env[k.key]} overridden={k.key in snap.overrides} can={can} onChange={(v) => set(k.key, v)} onReset={() => reset(k.key)} />)}
          </div>
          {g.id === 'agent' && (
            <div className="cfg-persona">
              <div className="cfg-label"><label htmlFor="cfg-persona" className="mono">persona</label></div>
              <select id="cfg-persona" className="mono" value={persona} onChange={(e) => { setPersona(e.target.value); setPreview(null) }}>{personaChoices.map((p) => <option key={p} value={p}>{p}</option>)}</select>
              {hasNote && <Field k={snap.schema.find((k) => k.key === noteKey)!} value={val(noteKey)} env="" overridden={noteKey in snap.overrides} can={can} onChange={(v) => set(noteKey, v)} onReset={() => reset(noteKey)} />}
              {hasTools && <ToolPicker persona={persona} snap={snap} value={(val(toolsKey) as string[] | null) ?? null} can={can} onChange={(v) => set(toolsKey, v)} />}
              <div className="btnrow">
                <button type="button" className="btn small" onClick={() => (preview ? setPreview(null) : refreshPreview(persona))} aria-expanded={!!preview} aria-controls="cfg-preview">{preview ? 'hide effective prompt' : 'preview effective prompt'}</button>
                {Object.keys(draft).some((k) => k.startsWith('agent.')) && <span className="muted small">preview shows the saved state</span>}
              </div>
              {preview && (
                <div id="cfg-preview" className="cfg-preview" data-testid="prompt-preview" tabIndex={0} aria-label="effective system prompt">
                  <div className="muted small mono">{preview.persona} · {preview.chars} chars · model {preview.model_id} · {preview.tools.length} tools: {preview.tools.join(' ')}</div>
                  <pre className="mono small">{preview.prompt}</pre>
                </div>
              )}
            </div>
          )}
          {g.id === 'telegram' && (
            <div className="cfg-secrets muted small mono" data-testid="secrets">
              {Object.entries(snap.secrets).map(([name, on]) => <span key={name} className={`chip ${on ? 'on' : ''}`} aria-label={`${name} ${on ? 'set' : 'unset'}`}>{name} {on ? 'set' : 'unset'}</span>)}
            </div>
          )}
          {saveRow(g.id, g.id === 'voice' ? 'apply (restarts voice, ~10 s)' : undefined)}
        </section>
      ))}

      <section className="cfg-section" aria-labelledby="cfg-personas-title">
        <h3 id="cfg-personas-title" className="dock-sub">personas</h3>
        <p className="muted small cfg-blurb">The systemd user units behind TINY. Settings apply without a restart; this is the fallback.</p>
        {units ? (
          <table className="cfg-units mono small" data-testid="personas">
            <thead><tr><th scope="col">unit</th><th scope="col">state</th><th scope="col">since</th><th scope="col"><span className="sr-only">actions</span></th></tr></thead>
            <tbody>
              {units.units.map((u) => (
                <tr key={u.unit}>
                  <td>{u.unit}</td>
                  <td><span className={`dot ${u.active === 'active' ? 'on' : ''}`} /> {u.active}{u.pid ? ` · pid ${u.pid}` : ''}</td>
                  <td>{since(u, units.t)}</td>
                  <td><button type="button" className="btn small" disabled={!can || busy !== '' || u.cooldown_s > 0} onClick={() => restart(u)} aria-label={`restart ${u.unit}`}>{u.cooldown_s > 0 ? `wait ${u.cooldown_s}s` : 'restart'}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="muted small">persona status unavailable</div>}
      </section>
    </div>
  )
}
