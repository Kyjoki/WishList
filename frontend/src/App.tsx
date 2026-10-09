import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { ArrowLeft, ArrowRight, Clapperboard, Dices, Gamepad2, Heart, LogOut, Plus, Search, Settings, Shield, Sparkles, X } from 'lucide-react'
import { api, json, type Candidate, type Item, type Kind, type Status, type User } from './api'
import { copy } from './i18n'

type Page = 'home' | 'collection' | 'manage' | 'settings' | 'users' | 'detail'
type Draft = { kind: Kind; title: string; year: string; status: Status; description: string; genres: string; image_url: string; source_url: string; source: string; external_id: string }
const emptyDraft = (kind: Kind = 'movie'): Draft => ({ kind, title: '', year: '', status: 'want', description: '', genres: '', image_url: '', source_url: '', source: '', external_id: '' })
const fromCandidate = (candidate: Candidate): Draft => ({ kind: candidate.kind, title: candidate.title, year: candidate.year?.toString() || '', status: 'want', description: candidate.description || '', genres: candidate.genres || '', image_url: candidate.image_url || '', source_url: candidate.source_url || '', source: candidate.source || '', external_id: candidate.external_id || '' })
const fromItem = (item: Item): Draft => ({ kind: item.kind, title: item.title, year: item.year?.toString() || '', status: item.status, description: item.description || '', genres: item.genres || '', image_url: item.image_url || '', source_url: item.source_url || '', source: item.source || '', external_id: item.external_id || '' })
const isLink = (value: string) => /^https?:\/\//i.test(value)
const validLink = (value: string) => !value || /^https?:\/\/[^\s/]+/i.test(value)

function Poster({ src, title, large = false }: { src?: string | null; title: string; large?: boolean }) {
  const [broken, setBroken] = useState(false)
  useEffect(() => setBroken(false), [src])
  return <div className={`poster ${large ? 'poster-large' : ''}`}>{src && !broken ? <img src={src} alt={title} loading="lazy" onError={() => setBroken(true)} /> : <div className="poster-fallback"><Sparkles size={large ? 50 : 32} strokeWidth={1.2} /><span>PLAY & WATCH</span></div>}</div>
}

function App() {
  const [me, setMe] = useState<User | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [page, setPage] = useState<Page>('home')
  const [items, setItems] = useState<Item[]>([])
  const [itemsLoading, setItemsLoading] = useState(false)
  const [error, setError] = useState('')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<Item | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [kind, setKind] = useState<'all' | Kind>('all')
  const [status, setStatus] = useState<'all' | Status>('all')
  const [query, setQuery] = useState('')
  const [genre, setGenre] = useState('')
  const [draft, setDraft] = useState<Draft>(emptyDraft())
  const [editingId, setEditingId] = useState<number | null>(null)
  const [lookup, setLookup] = useState('')
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [lookupMessage, setLookupMessage] = useState('')
  const [looking, setLooking] = useState(false)
  const [saving, setSaving] = useState(false)
  const [note, setNote] = useState('')
  const [users, setUsers] = useState<User[]>([])
  const [newUser, setNewUser] = useState({ username: '', password: '', role: 'friend' as 'friend' | 'admin' })
  const t = copy[me?.language || 'ru']

  useEffect(() => { api<User>('/me').then(setMe).catch(() => {}).finally(() => setAuthLoading(false)) }, [])
  useEffect(() => { if (me) loadItems() }, [me?.id])
  useEffect(() => { if (me && selectedId != null) loadDetail(selectedId) }, [selectedId, me?.language])
  useEffect(() => { if (page === 'users' && me?.role === 'admin') loadUsers() }, [page])

  async function loadItems() {
    setItemsLoading(true)
    try { setItems(await api<Item[]>('/items')); setError('') } catch (e) { setError((e as Error).message) } finally { setItemsLoading(false) }
  }
  async function loadDetail(id: number) {
    setDetailLoading(true)
    try { setDetail(await api<Item>(`/items/${id}`)); setError('') } catch (e) { setError((e as Error).message) } finally { setDetailLoading(false) }
  }
  async function loadUsers() { try { setUsers(await api<User[]>('/users')) } catch (e) { setError((e as Error).message) } }
  function openItem(id: number) { setSelectedId(id); setPage('detail'); setError(''); window.scrollTo(0, 0) }
  function go(next: Page) { setPage(next); setError(''); window.scrollTo(0, 0) }
  function beginAdd() { setEditingId(null); setDraft(emptyDraft()); setLookup(''); setCandidates([]); setLookupMessage(''); go('manage') }

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError('')
    const data = new FormData(event.currentTarget)
    try { const user = await api<User>('/login', json({ username: data.get('username'), password: data.get('password') })); setMe(user); go('home') }
    catch (e) { setError((e as Error).message) }
  }
  async function signOut() { await api('/logout', { method: 'POST' }).catch(() => {}); setMe(null); setItems([]); setDetail(null); go('home') }
  async function lookupMetadata(event: FormEvent) {
    event.preventDefault(); setLooking(true); setError(''); setCandidates([]); setLookupMessage('')
    try {
      if (isLink(lookup)) {
        const result = await api<{ available: boolean; item: Candidate | null; message: string }>(`/metadata/link?url=${encodeURIComponent(lookup)}`)
        if (result.item) setDraft(fromCandidate(result.item))
        else { setDraft({ ...emptyDraft(draft.kind), source_url: lookup }); setLookupMessage(t.unavailable) }
      } else {
        const result = await api<{ available: boolean; results: Candidate[]; message: string }>(`/metadata/search?kind=${draft.kind}&query=${encodeURIComponent(lookup.trim())}`)
        setCandidates(result.results)
        if (!result.available) setLookupMessage(t.unavailable)
        else if (!result.results.length) setLookupMessage(t.noCandidates)
      }
    } catch (e) { setLookupMessage(t.unavailable); setError((e as Error).message) }
    finally { setLooking(false) }
  }
  async function selectCandidate(candidate: Candidate) {
    setCandidates([])
    setDraft(fromCandidate(candidate))
    if (!candidate.source_url) return
    try {
      const result = await api<{ item: Candidate | null }>(`/metadata/link?url=${encodeURIComponent(candidate.source_url)}`)
      if (result.item) setDraft(fromCandidate(result.item))
    } catch { /* The searchable candidate is still usable if the detail request fails. */ }
  }
  async function saveItem(event: FormEvent) {
    event.preventDefault(); setError('')
    if (!draft.title.trim() || !validLink(draft.image_url) || !validLink(draft.source_url)) { setError(t.validation); return }
    setSaving(true)
    const payload = { kind: draft.kind, title: draft.title.trim(), year: draft.year ? Number(draft.year) : null, status: draft.status,
      description: draft.description, genres: draft.genres, image_url: draft.image_url || null, source_url: draft.source_url || null,
      ...(!editingId ? { source: draft.source || null, external_id: draft.external_id || null } : {}) }
    try {
      const item = await api<Item>(editingId ? `/items/${editingId}` : '/items', json(payload, editingId ? 'PATCH' : 'POST'))
      await loadItems(); setEditingId(null); setDraft(emptyDraft()); openItem(item.id)
    } catch (e) { setError((e as Error).message) } finally { setSaving(false) }
  }
  async function changeStatus(next: Status) {
    if (!detail) return
    try { await api(`/items/${detail.id}`, json({ status: next }, 'PATCH')); await Promise.all([loadDetail(detail.id), loadItems()]) }
    catch (e) { setError((e as Error).message) }
  }
  async function addNote(event: FormEvent) {
    event.preventDefault(); if (!detail || !note.trim()) return
    try { await api(`/items/${detail.id}/notes`, json({ text: note.trim() })); setNote(''); await loadDetail(detail.id) }
    catch (e) { setError((e as Error).message) }
  }
  async function removeItem() {
    if (!detail || !confirm(t.confirmDelete)) return
    try { await api(`/items/${detail.id}`, { method: 'DELETE' }); await loadItems(); setDetail(null); go('collection') }
    catch (e) { setError((e as Error).message) }
  }
  async function removeManagedItem(id: number) {
    if (!confirm(t.confirmDelete)) return
    try { await api(`/items/${id}`, { method: 'DELETE' }); await loadItems() }
    catch (e) { setError((e as Error).message) }
  }
  async function randomItem() {
    try { const item = await api<Item>(`/items/random${kind !== 'all' ? `?kind=${kind}` : ''}`); openItem(item.id) }
    catch { setError(t.randomEmpty) }
  }
  async function setLanguage(language: 'ru' | 'en') {
    try { setMe(await api<User>('/me', json({ language }, 'PATCH'))); if (selectedId) loadDetail(selectedId) }
    catch (e) { setError((e as Error).message) }
  }
  async function createUser(event: FormEvent) {
    event.preventDefault()
    try { await api('/users', json(newUser)); setNewUser({ username: '', password: '', role: 'friend' }); await loadUsers(); setError('') }
    catch (e) { setError((e as Error).message) }
  }
  async function changeUser(id: number, body: object) {
    try { await api(`/users/${id}`, json(body, 'PATCH')); await loadUsers(); setError('') }
    catch (e) { setError((e as Error).message) }
  }
  async function removeUser(id: number) {
    if (!confirm(t.confirmDelete)) return
    try { await api(`/users/${id}`, { method: 'DELETE' }); await loadUsers() }
    catch (e) { setError((e as Error).message) }
  }

  const shown = useMemo(() => items.filter(item => {
    const kindMatch = kind === 'all' || item.kind === kind || (kind === 'movie' && item.kind === 'series')
    return kindMatch && (status === 'all' || item.status === status) && (!query || `${item.title} ${item.genres}`.toLowerCase().includes(query.toLowerCase()))
  }), [items, kind, status, query])
  const watching = items.filter(item => item.kind !== 'game')
  const playing = items.filter(item => item.kind === 'game')
  const genres = [...new Set(items.flatMap(item => item.genres.split(',').map(g => g.trim()).filter(Boolean)))].slice(0, 5)
  const homeFiltered = items.filter(item => (!query || `${item.title} ${item.genres}`.toLowerCase().includes(query.toLowerCase())) && (!genre || item.genres.toLowerCase().includes(genre.toLowerCase())) && (status === 'all' || item.status === status))
  const homeWatching = homeFiltered.filter(item => item.kind !== 'game')
  const homePlaying = homeFiltered.filter(item => item.kind === 'game')
  const labelKind = (value: Kind) => t[value]
  const labelStatus = (value: Status, itemKind: Kind) => value === 'want' ? t.wanted : value === 'active' ? (itemKind === 'game' ? t.activePlay : t.activeWatch) : value === 'done' ? t.done : t.paused
  function Card({ item }: { item: Item }) { return <button className="item-card" onClick={() => openItem(item.id)}><div className="card-poster"><Poster src={item.image_url} title={item.title} /><span className={`poster-status ${item.status}`}>{labelStatus(item.status, item.kind)}</span></div><div className="card-body"><h3>{item.title}</h3><span className="card-meta">{item.year || '—'} · {item.genres.split(',')[0]?.trim() || labelKind(item.kind)}</span></div></button> }

  if (authLoading) return <div className="center-screen">{t.loading}</div>
  if (!me) return <div className="login-shell"><div className="login-art"><div className="brand"><span className="brand-icon"><Clapperboard size={20} /><Gamepad2 size={20} /></span> Play & Watch</div><div className="login-orb orb-one"/><div className="login-orb orb-two"/><div className="login-tag">ЛУЧШЕЕ — ВМЕСТЕ</div><h1>{t.welcome}</h1><p>{t.subtitle}</p><div className="art-bottom"><span>01 / 02</span><span>✦ &nbsp; PLAY & WATCH</span></div></div><div className="login-panel"><div className="login-form"><div className="mobile-brand">✦ &nbsp; Play & Watch</div><span className="eyebrow accent">{t.login}</span><h2>{t.signInTitle}</h2><p>{t.signInText}</p>{error && <div className="alert">{error}</div>}<form onSubmit={signIn}><label>{t.username}<input name="username" autoComplete="username" required /></label><label>{t.password}<input name="password" type="password" autoComplete="current-password" required /></label><button className="primary full" type="submit">{t.login}<ArrowRight size={18}/></button></form><small>PLAY & WATCH · PRIVATE SPACE</small></div></div></div>

  return <div className="app-shell">
    <header className="topbar"><button className="brand" onClick={() => go('home')}><span>Play<i>&</i>Watch</span></button><nav><button className={page === 'home' && kind !== 'game' ? 'nav-active' : ''} onClick={() => { setKind('movie'); go('home') }}>{t.watch}</button><button className={page === 'home' && kind === 'game' ? 'nav-active' : ''} onClick={() => { setKind('game'); go('home') }}>{t.play}</button><button className={page === 'collection' ? 'nav-active' : ''} onClick={() => go('collection')}>{t.collection}</button><button className={page === 'manage' ? 'nav-active' : ''} onClick={() => go('manage')}>{t.manage}</button></nav><div className="top-actions"><button className="language-switch" onClick={() => setLanguage(me.language === 'ru' ? 'en' : 'ru')} title={t.language}><b>{me.language.toUpperCase()}</b><span>/ {me.language === 'ru' ? 'EN' : 'RU'}</span></button><button className="icon-button" aria-label={t.settings} onClick={() => go('settings')}><Settings size={19}/></button><button className="avatar" onClick={() => go('settings')} title={me.username}>{me.username.charAt(0).toUpperCase()}</button></div></header>
    <main>
      {error && <div className="alert global-alert"><span>{error}</span><button onClick={() => setError('')} aria-label="Close"><X size={16}/></button></div>}
      {page === 'home' && <><section className="home-tools"><div className="home-search-row"><div className="search-box"><Search size={18}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder={t.search}/></div><button className="primary random" onClick={randomItem}><Dices size={17}/>{t.random}</button><button className="secondary add-outline" onClick={beginAdd}><Plus size={17}/>{t.add}</button></div><div className="home-chips"><div className="chip-group"><button className={!genre ? 'selected' : ''} onClick={() => setGenre('')}>{t.all}</button>{genres.map(value => <button key={value} className={genre === value ? 'selected' : ''} onClick={() => setGenre(value)}>{value}</button>)}</div><div className="chip-group"><button className={status === 'all' ? 'selected' : ''} onClick={() => setStatus('all')}>{t.all}</button><button className={status === 'want' ? 'selected' : ''} onClick={() => setStatus('want')}>{t.wanted}</button><button className={status === 'active' ? 'selected' : ''} onClick={() => setStatus('active')}>{t.activeWatch}/{t.activePlay}</button><button className={status === 'done' ? 'selected' : ''} onClick={() => setStatus('done')}>{t.done}</button><button className={status === 'paused' ? 'selected' : ''} onClick={() => setStatus('paused')}>{t.paused}</button></div></div></section><section className="hero"><div className="hero-content"><div className="pill"><span className="pulse"/> YOUR SHARED SPACE</div><h1>{t.welcome}</h1><p>{t.subtitle}</p><div className="hero-buttons"><button className="primary" onClick={() => go('collection')}>{t.explore}<ArrowRight size={18}/></button><button className="secondary" onClick={beginAdd}><Plus size={18}/>{t.addNew}</button></div><div className="hero-stats"><div><b>{items.length.toString().padStart(2,'0')}</b><span>{t.all}</span></div><div><b>{watching.length.toString().padStart(2,'0')}</b><span>{t.watch}</span></div><div><b>{playing.length.toString().padStart(2,'0')}</b><span>{t.play}</span></div></div></div><div className="hero-visual"><div className="visual-ring ring-a"/><div className="visual-ring ring-b"/><div className="floating-card float-one"><Clapperboard size={32}/><span>{t.watch}</span></div><div className="floating-card float-two"><Gamepad2 size={38}/><span>{t.play}</span></div><div className="visual-star">✦</div></div></section>
        {kind !== 'game' && <section className="section"><div className="section-heading"><div><span className="eyebrow accent">01 / WATCHLIST</span><h2>{t.watch}</h2><p>{me.language === 'ru' ? 'Фильмы и сериалы' : 'Movies & series'}</p></div><button className="text-link" onClick={() => { setKind('movie'); go('collection') }}>{t.all}<ArrowRight size={16}/></button></div><div className="card-grid">{homeWatching.slice(0, 6).map(item => <Card key={item.id} item={item}/>)}</div>{!homeWatching.length && <div className="empty-state"><Clapperboard size={32}/><p>{watching.length ? t.noResults : t.noItems}</p>{!watching.length && <button onClick={beginAdd}>{t.addNew}</button>}</div>}</section>}
        {kind !== 'movie' && <section className="section"><div className="section-heading"><div><span className="eyebrow accent">02 / GAME LIBRARY</span><h2>{t.play}</h2><p>{me.language === 'ru' ? 'Игры для нового приключения' : 'Games for the next adventure'}</p></div><button className="text-link" onClick={() => { setKind('game'); go('collection') }}>{t.all}<ArrowRight size={16}/></button></div><div className="card-grid">{homePlaying.slice(0, 6).map(item => <Card key={item.id} item={item}/>)}</div>{!homePlaying.length && <div className="empty-state"><Gamepad2 size={32}/><p>{playing.length ? t.noResults : t.noItems}</p>{!playing.length && <button onClick={beginAdd}>{t.addNew}</button>}</div>}</section>}</>}
      {page === 'collection' && <section className="page-section"><div className="page-heading"><div><span className="eyebrow accent">YOUR SHARED UNIVERSE</span><h1>{t.collection}</h1><p>{items.length} {t.all.toLowerCase()}</p></div><button className="primary" onClick={beginAdd}><Plus size={18}/>{t.add}</button></div><div className="filters"><div className="search-box"><Search size={18}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder={t.search}/></div><select value={kind} onChange={e => setKind(e.target.value as typeof kind)}><option value="all">{t.all}</option><option value="movie">{t.watch}</option><option value="game">{t.play}</option></select><select value={status} onChange={e => setStatus(e.target.value as typeof status)}><option value="all">{t.all}</option><option value="want">{t.wanted}</option><option value="active">{t.activeWatch}/{t.activePlay}</option><option value="done">{t.done}</option><option value="paused">{t.paused}</option></select><button className="secondary random" onClick={randomItem}><Dices size={18}/>{t.random}</button></div>{itemsLoading ? <div className="loading-state">{t.loading}</div> : <div className="card-grid collection-grid">{shown.map(item => <Card key={item.id} item={item}/>)}</div>}{!itemsLoading && !shown.length && <div className="empty-state"><Heart size={32}/><p>{items.length ? t.noResults : t.noItems}</p>{!items.length && <button onClick={beginAdd}>{t.addNew}</button>}</div>}</section>}
      {page === 'manage' && <section className="page-section manage-page"><div className="page-heading"><div><span className="eyebrow accent">CURATE THE LIST</span><h1>{editingId ? t.edit : t.manage}</h1><p>{t.introManage}</p></div>{me.role === 'admin' && <button className="secondary" onClick={() => go('users')}><Shield size={17}/>{t.users}</button>}</div><div className="manage-stats"><div className="panel"><small>{t.all}</small><strong>{items.length}</strong></div><div className="panel"><small>{t.wanted}</small><strong>{items.filter(x => x.status === 'want').length}</strong></div><div className="panel"><small>{t.done}</small><strong>{items.filter(x => x.status === 'done').length}</strong></div></div><div className="manage-columns"><div className="manage-records panel"><div className="section-heading"><h2>{t.collection}</h2><span className="muted">{items.length}</span></div>{items.length ? items.map(item => <div className="manage-record" key={item.id}><button onClick={() => openItem(item.id)}><strong>{item.title}</strong><small>{labelKind(item.kind)} · {item.year || '—'}</small></button><span className={`status-label ${item.status}`}>{labelStatus(item.status,item.kind)}</span>{me.role === 'admin' && <div><button className="text-link" onClick={() => { setDraft(fromItem(item)); setEditingId(item.id); setLookup(''); setCandidates([]); window.scrollTo(0,0) }}>{t.edit}</button><button className="danger-link" onClick={() => removeManagedItem(item.id)}>{t.delete}</button></div>}</div>) : <p className="muted">{t.noItems}</p>}</div><div className="manage-layout"><div className="panel"><div className="panel-title"><span className="step-number">01</span><div><h2>{t.find}</h2><p>{t.searchMeta}</p></div></div><div className="segmented"><button className={draft.kind === 'movie' ? 'selected' : ''} onClick={() => { setDraft(emptyDraft('movie')); setCandidates([]) }}>{t.movie}</button><button className={draft.kind === 'series' ? 'selected' : ''} onClick={() => { setDraft(emptyDraft('series')); setCandidates([]) }}>{t.series}</button><button className={draft.kind === 'game' ? 'selected' : ''} onClick={() => { setDraft(emptyDraft('game')); setCandidates([]) }}>{t.game}</button></div><form className="lookup-row" onSubmit={lookupMetadata}><input value={lookup} onChange={e => setLookup(e.target.value)} placeholder={t.searchMeta} required minLength={2}/><button className="primary" disabled={looking}>{looking ? t.loading : t.find}</button></form><button className="text-link manual-button" onClick={() => { setDraft({ ...emptyDraft(draft.kind), source_url: isLink(lookup) ? lookup : '' }); setCandidates([]) }}><Plus size={16}/>{t.manual}</button>{lookupMessage && <div className="info-box">{lookupMessage}</div>}</div>
        {!!candidates.length && <div className="panel"><div className="panel-title"><span className="step-number">02</span><div><h2>{t.candidates}</h2><p>{candidates.length} matches</p></div></div><div className="candidate-list">{candidates.map((candidate, index) => <button key={`${candidate.source}-${candidate.external_id}-${index}`} onClick={() => selectCandidate(candidate)}><Poster src={candidate.image_url} title={candidate.title}/><span><strong>{candidate.title}</strong><small>{candidate.year || '—'} · {labelKind(candidate.kind)}</small></span><ArrowRight size={18}/></button>)}</div></div>}
        <div className="panel"><div className="panel-title"><span className="step-number">{candidates.length ? '03' : '02'}</span><div><h2>{t.addNew}</h2><p>{t.verify}</p></div></div><form className="item-form" onSubmit={saveItem}><div className="form-grid"><label>{t.title}<input value={draft.title} onChange={e => setDraft({...draft,title:e.target.value})} required maxLength={200}/></label><label>{t.year}<input type="number" min="1880" max="2100" value={draft.year} onChange={e => setDraft({...draft,year:e.target.value})}/></label><label>{t.type}<select value={draft.kind} onChange={e => setDraft({...draft,kind:e.target.value as Kind})}><option value="movie">{t.movie}</option><option value="series">{t.series}</option><option value="game">{t.game}</option></select></label><label>{t.status}<select value={draft.status} onChange={e => setDraft({...draft,status:e.target.value as Status})}><option value="want">{t.wanted}</option><option value="active">{t.activeWatch}/{t.activePlay}</option><option value="done">{t.done}</option><option value="paused">{t.paused}</option></select></label></div><label>{t.genres}<input value={draft.genres} onChange={e => setDraft({...draft,genres:e.target.value})} maxLength={500}/></label><label>{t.description}<textarea rows={4} value={draft.description} onChange={e => setDraft({...draft,description:e.target.value})} maxLength={10000}/></label><div className="form-grid"><label>{t.image}<input type="url" value={draft.image_url} onChange={e => setDraft({...draft,image_url:e.target.value})} placeholder="https://"/></label><label>{t.source}<input type="url" value={draft.source_url} onChange={e => setDraft({...draft,source_url:e.target.value})} placeholder="https://"/></label></div><div className="form-actions"><button type="submit" className="primary" disabled={saving}>{saving ? t.loading : t.save}<ArrowRight size={17}/></button>{editingId && <button type="button" className="secondary" onClick={beginAdd}>{t.cancel}</button>}</div></form></div></div></div></section>}
      {page === 'detail' && <section className="page-section"><button className="back-link" onClick={() => go('collection')}><ArrowLeft size={17}/>{t.collection}</button>{detailLoading ? <div className="loading-state">{t.loading}</div> : detail && <><div className="detail-layout"><Poster src={detail.image_url} title={detail.title} large/><div className="detail-content"><span className="eyebrow accent">{labelKind(detail.kind)} · {detail.year || '—'}</span><h1>{detail.title}</h1><div className="detail-meta"><span>{detail.year || '—'}</span><span>{labelKind(detail.kind)}</span><span className={`status-label ${detail.status}`}>{labelStatus(detail.status, detail.kind)}</span></div><p className="description">{detail.description || '—'}</p>{detail.genres && <div className="genre-list">{detail.genres.split(',').map(g => <span key={g.trim()}>{g.trim()}</span>)}</div>}<div className="detail-actions">{detail.source_url && <a className="secondary" href={detail.source_url} target="_blank" rel="noopener noreferrer">{t.openSource}<ArrowRight size={16}/></a>}{me.role === 'admin' && <><button className="secondary" onClick={() => { setDraft(fromItem(detail)); setEditingId(detail.id); go('manage') }}>{t.edit}</button><button className="danger-button" onClick={removeItem}>{t.delete}</button></>}</div>{detail.source && <a className="credit-link" href={detail.source === 'tmdb' ? 'https://www.themoviedb.org' : 'https://rawg.io'} target="_blank" rel="noopener noreferrer">Data & images: {detail.source === 'tmdb' ? 'TMDB' : 'RAWG'} ↗</a>}</div></div><div className="detail-bottom"><div className="panel"><h2>{t.status}</h2><div className="status-buttons">{(['want','active','done','paused'] as Status[]).map(value => <button key={value} className={detail.status === value ? 'selected' : ''} onClick={() => changeStatus(value)}>{labelStatus(value, detail.kind)}</button>)}</div><h2>{t.history}</h2><div className="timeline">{detail.history?.map((event, index) => <div key={index}><span className="timeline-dot"/><div><strong>{labelStatus(event.status, detail.kind)}</strong><small>{event.username} · {new Date(event.created_at + 'Z').toLocaleDateString(me.language)}</small></div></div>)}</div></div><div className="panel"><h2>{t.notes}</h2><form className="note-form" onSubmit={addNote}><textarea value={note} onChange={e => setNote(e.target.value)} placeholder={t.note} rows={3} maxLength={2000}/><button className="primary" disabled={!note.trim()}>{t.addNote}</button></form><div className="notes-list">{detail.notes?.length ? detail.notes.map(entry => <div className="note-card" key={entry.id}><div className="note-author"><span className="small-avatar">{entry.username.charAt(0).toUpperCase()}</span><strong>{entry.username}</strong><small>{new Date(entry.created_at + 'Z').toLocaleDateString(me.language)}</small></div><p>{entry.text}</p></div>) : <p className="muted">{t.noNotes}</p>}</div></div></div></>}</section>}
      {page === 'settings' && <section className="page-section narrow"><div className="page-heading"><div><span className="eyebrow accent">PREFERENCES</span><h1>{t.settings}</h1></div></div><div className="panel settings-panel"><div className="profile-row"><span className="avatar large-avatar">{me.username.charAt(0).toUpperCase()}</span><div><h2>{me.username}</h2><p>{me.role === 'admin' ? t.admin : t.friend}</p></div></div><div className="setting-row"><div><h3>{t.language}</h3><p>Русский / English</p></div><div className="segmented compact"><button className={me.language === 'ru' ? 'selected' : ''} onClick={() => setLanguage('ru')}>RU</button><button className={me.language === 'en' ? 'selected' : ''} onClick={() => setLanguage('en')}>EN</button></div></div>{me.role === 'admin' && <button className="setting-link" onClick={() => go('users')}><Shield size={19}/>{t.users}<ArrowRight size={17}/></button>}<button className="setting-link" onClick={signOut}><LogOut size={19}/>{t.logout}<ArrowRight size={17}/></button></div></section>}
      {page === 'users' && me.role === 'admin' && <section className="page-section narrow"><button className="back-link" onClick={() => go('settings')}><ArrowLeft size={17}/>{t.settings}</button><div className="page-heading"><div><span className="eyebrow accent">ADMINISTRATION</span><h1>{t.users}</h1></div></div><div className="panel"><h2>{t.newUser}</h2><form className="user-create" onSubmit={createUser}><input placeholder={t.username} value={newUser.username} onChange={e => setNewUser({...newUser,username:e.target.value})} pattern="[a-zA-Z0-9_-]{3,32}" required/><input placeholder={t.password} type="password" minLength={12} value={newUser.password} onChange={e => setNewUser({...newUser,password:e.target.value})} required/><select value={newUser.role} onChange={e => setNewUser({...newUser,role:e.target.value as 'friend' | 'admin'})}><option value="friend">{t.friend}</option><option value="admin">{t.admin}</option></select><button className="primary">{t.create}</button></form></div><div className="panel users-panel">{users.map(user => <div className="user-row" key={user.id}><span className="small-avatar">{user.username.charAt(0).toUpperCase()}</span><div><strong>{user.username}</strong><small>{user.role === 'admin' ? t.admin : t.friend} · {user.language.toUpperCase()}</small></div><div className="user-controls">{user.id !== me.id && <><select value={user.role} onChange={e => changeUser(user.id, { role: e.target.value })}><option value="friend">{t.friend}</option><option value="admin">{t.admin}</option></select><button className="danger-button" onClick={() => removeUser(user.id)}>{t.delete}</button></>}<button className="text-link" onClick={() => { const password = prompt(t.resetPassword); if (password) changeUser(user.id, { password }) }}>{t.resetPassword}</button></div></div>)}</div></section>}
    </main><footer><div className="footer-brand">✦ &nbsp; Play & Watch</div><p>{t.credits} This product uses the TMDB API but is not endorsed or certified by TMDB. <a href="https://www.themoviedb.org" target="_blank" rel="noopener noreferrer">TMDB ↗</a> · <a href="https://rawg.io" target="_blank" rel="noopener noreferrer">RAWG ↗</a></p><a className="tmdb-logo" href="https://www.themoviedb.org" target="_blank" rel="noopener noreferrer" aria-label="TMDB"><img src="https://www.themoviedb.org/assets/2/v4/logos/v2/blue_square_2-d537fb228cf3ded904ef09b136fe3fec72548ebc1fea3fbbd1ad9e36364db38b.svg" alt="TMDB" /></a></footer>
  </div>
}

export default App
