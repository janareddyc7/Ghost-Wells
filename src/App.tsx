import { useState } from 'react'
import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronDown,
  CircleHelp,
  Database,
  Download,
  ExternalLink,
  FileSearch,
  Layers3,
  MapPinned,
  Menu,
  Radio,
  ScanSearch,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  X,
} from 'lucide-react'

type View = 'overview' | 'survey' | 'pipeline' | 'about'
type SheetStatus = 'Queued' | 'Needs review' | 'Reviewed'

const sheets: {
  name: string
  county: string
  edition: string
  status: SheetStatus
  symbols: string
}[] = [
  {
    name: 'Macksburg',
    county: 'Washington',
    edition: 'Historical edition',
    status: 'Queued',
    symbols: '—',
  },
  {
    name: 'Lowell',
    county: 'Washington',
    edition: 'Historical edition',
    status: 'Queued',
    symbols: '—',
  },
  {
    name: 'Findlay',
    county: 'Hancock',
    edition: 'Historical edition',
    status: 'Queued',
    symbols: '—',
  },
  {
    name: 'North Baltimore',
    county: 'Wood',
    edition: 'Historical edition',
    status: 'Queued',
    symbols: '—',
  },
  {
    name: 'Medina',
    county: 'Medina',
    edition: 'Historical edition',
    status: 'Queued',
    symbols: '—',
  },
  {
    name: 'Lodi',
    county: 'Medina',
    edition: 'Historical edition',
    status: 'Queued',
    symbols: '—',
  },
]

const stages = [
  {
    number: '01',
    title: 'Find the maps',
    body: 'Collect named Ohio sheets and edition metadata from the USGS archive.',
    icon: MapPinned,
    state: 'First gate',
  },
  {
    number: '02',
    title: 'Read the symbols',
    body: 'Review map crops, distinguish well symbols from lookalikes, and measure coverage.',
    icon: ScanSearch,
    state: 'Planned',
  },
  {
    number: '03',
    title: 'Cross-check records',
    body: 'Compare mapped symbols with a dated ODNR well inventory and inspect uncertain matches.',
    icon: Database,
    state: 'Planned',
  },
  {
    number: '04',
    title: 'Review the leads',
    body: 'Keep exact locations private and package evidence for qualified agency review.',
    icon: ShieldCheck,
    state: 'Planned',
  },
]

function Brand() {
  return (
    <div className="brand" aria-label="Ghost Wells home">
      <div className="brand-mark">
        <span className="brand-ring" />
        <span className="brand-dot" />
      </div>
      <div className="brand-text">
        GHOST<span>WELLS</span>
        <small>OHIO RESEARCH WORKSPACE</small>
      </div>
    </div>
  )
}

function Tag({
  children,
  tone = 'neutral',
}: {
  children: React.ReactNode
  tone?: 'neutral' | 'amber' | 'green'
}) {
  return <span className={`tag tag-${tone}`}>{children}</span>
}

function MapArt() {
  return (
    <div
      className="map-art"
      role="img"
      aria-label="Decorative topographic map illustration; no real well locations are shown"
    >
      <div className="map-grid" />
      <svg
        className="contours"
        viewBox="0 0 620 410"
        preserveAspectRatio="xMidYMid slice"
        aria-hidden="true"
      >
        <g fill="none" stroke="currentColor" strokeWidth="1.4">
          <path d="M-90 334 C58 320 64 408 206 381 S327 246 450 295 S577 363 710 234" />
          <path d="M-83 303 C36 286 103 371 213 350 S326 213 452 266 S565 331 706 205" />
          <path d="M-82 272 C34 249 123 339 213 317 S324 184 449 236 S557 301 701 178" />
          <path d="M-79 238 C43 218 125 309 215 286 S323 153 447 204 S555 270 698 150" />
          <path d="M-75 205 C40 184 132 275 215 255 S323 124 446 174 S558 242 696 118" />
          <path d="M-68 171 C38 151 134 246 214 223 S322 91 447 142 S560 213 695 87" />
          <path d="M-55 138 C39 115 138 217 215 192 S324 60 450 110 S561 182 691 57" />
          <path d="M-34 107 C40 84 135 188 212 161 S321 28 448 79 S560 148 679 25" />
          <path d="M-15 77 C40 48 137 160 211 129 S326 -6 453 47 S559 121 655 -8" />
        </g>
        <path
          d="M88 -20 C143 81 192 123 256 180 S376 259 403 439"
          fill="none"
          stroke="#b2c2aa"
          strokeWidth="18"
          opacity=".45"
        />
        <path
          d="M88 -20 C143 81 192 123 256 180 S376 259 403 439"
          fill="none"
          stroke="#e6e9d4"
          strokeWidth="9"
          opacity=".7"
        />
      </svg>
      <div className="map-label map-label-a">WASHINGTON CO.</div>
      <div className="map-label map-label-b">HISTORICAL SHEET · SAMPLE</div>
      <div className="map-target target-one">
        <span />
      </div>
      <div className="map-target target-two">
        <span />
      </div>
      <div className="map-target target-three">
        <span />
      </div>
      <div className="map-coordinate">39°33′ N &nbsp; 81°26′ W</div>
      <div className="map-corner">
        <Layers3 size={15} /> RESEARCH VIEW
      </div>
    </div>
  )
}

function App() {
  const [view, setView] = useState<View>('overview')
  const [menuOpen, setMenuOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('All statuses')
  const filtered = sheets.filter(
    (sheet) =>
      `${sheet.name} ${sheet.county}`.toLowerCase().includes(query.toLowerCase()) &&
      (statusFilter === 'All statuses' || sheet.status === statusFilter),
  )

  function navigate(next: View) {
    setView(next)
    setMenuOpen(false)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <div className="site-shell">
      <aside className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`}>
        <Brand />
        <div className="sidebar-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          <button
            className={`nav-item ${view === 'overview' ? 'active' : ''}`}
            onClick={() => navigate('overview')}
          >
            <Activity size={18} /> Overview
          </button>
          <button
            className={`nav-item ${view === 'survey' ? 'active' : ''}`}
            onClick={() => navigate('survey')}
          >
            <MapPinned size={18} /> Sheet survey <span className="nav-count">06</span>
          </button>
          <button
            className={`nav-item ${view === 'pipeline' ? 'active' : ''}`}
            onClick={() => navigate('pipeline')}
          >
            <Layers3 size={18} /> Method & stages
          </button>
        </nav>
        <div className="sidebar-label sidebar-label-second">PROJECT</div>
        <nav aria-label="Project navigation">
          <button
            className={`nav-item ${view === 'about' ? 'active' : ''}`}
            onClick={() => navigate('about')}
          >
            <BookOpen size={18} /> About the project
          </button>
          <a
            className="nav-item"
            href="https://ngmdb.usgs.gov/topoview/"
            target="_blank"
            rel="noreferrer"
          >
            <ExternalLink size={18} /> USGS topoView
          </a>
        </nav>
        <div className="sidebar-bottom">
          <span className="sidebar-pulse" /> STAGE 0 · RESEARCH IN PROGRESS{' '}
          <small>Independent project · Not affiliated with ODNR</small>
        </div>
      </aside>

      <div className="main-shell">
        <header className="topbar">
          <button
            className="mobile-menu icon-button"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            onClick={() => setMenuOpen(!menuOpen)}
          >
            {menuOpen ? <X size={21} /> : <Menu size={21} />}
          </button>
          <div className="breadcrumbs">
            GHOST WELLS <span>/</span>{' '}
            <strong>
              {view === 'overview'
                ? 'Overview'
                : view === 'survey'
                  ? 'Sheet survey'
                  : view === 'pipeline'
                    ? 'Method & stages'
                    : 'About the project'}
            </strong>
          </div>
          <div className="topbar-right">
            <span className="status-light" /> RESEARCH MODE{' '}
            <span className="topbar-divider" />{' '}
            <CircleHelp size={17} aria-label="Research status" />
          </div>
        </header>

        <main>
          {view === 'overview' && (
            <>
              <section className="hero">
                <div className="hero-copy">
                  <div className="eyebrow">
                    <span /> HISTORICAL MAP INTELLIGENCE / OHIO
                  </div>
                  <h1>
                    What did the old
                    <br />
                    <em>maps remember?</em>
                  </h1>
                  <p>
                    Exploring century-old topographic maps for traces of Ohio’s forgotten
                    oil and gas wells. Every lead begins with evidence. Every conclusion
                    requires review.
                  </p>
                  <div className="hero-actions">
                    <button className="button-primary" onClick={() => navigate('survey')}>
                      Explore the survey <ArrowUpRight size={18} />
                    </button>
                    <button className="button-text" onClick={() => navigate('pipeline')}>
                      How it works <ArrowRight size={17} />
                    </button>
                  </div>
                </div>
                <MapArt />
                <div className="hero-index">
                  01 / 04 <span>THE RESEARCH</span>
                </div>
              </section>

              <section className="disclosure">
                <div className="disclosure-icon">
                  <Radio size={18} />
                </div>
                <div>
                  <strong>Research status: source survey underway</strong>
                  <p>
                    Ohio map symbols have not yet been confirmed in this repository. The
                    map graphic is illustrative; no real candidate locations are
                    displayed.
                  </p>
                </div>
                <ArrowUpRight size={18} />
              </section>

              <section className="section-block">
                <div className="section-heading">
                  <div>
                    <div className="kicker">THE FIRST QUESTION</div>
                    <h2>Start with the source.</h2>
                  </div>
                  <p>
                    Before the model, the database, or the map, we need to know which Ohio
                    sheets actually show individual well symbols.
                  </p>
                </div>
                <div className="metric-grid">
                  <div className="metric-card">
                    <div className="metric-top">
                      <MapPinned size={20} />
                      <ArrowUpRight size={16} />
                    </div>
                    <div className="metric-value">06</div>
                    <div className="metric-label">Pilot sheets queued</div>
                    <div className="metric-note">Across three Ohio regions</div>
                  </div>
                  <div className="metric-card">
                    <div className="metric-top">
                      <ScanSearch size={20} />
                      <ArrowUpRight size={16} />
                    </div>
                    <div className="metric-value">—</div>
                    <div className="metric-label">Symbols confirmed</div>
                    <div className="metric-note">Awaiting reviewed scans</div>
                  </div>
                  <div className="metric-card">
                    <div className="metric-top">
                      <Database size={20} />
                      <ArrowUpRight size={16} />
                    </div>
                    <div className="metric-value">—</div>
                    <div className="metric-label">Record matches</div>
                    <div className="metric-note">ODNR comparison is a later stage</div>
                  </div>
                </div>
              </section>

              <section className="section-block process-section">
                <div className="section-heading">
                  <div>
                    <div className="kicker">WORKFLOW</div>
                    <h2>From ink to evidence.</h2>
                  </div>
                  <button className="inline-link" onClick={() => navigate('pipeline')}>
                    View full method <ArrowUpRight size={17} />
                  </button>
                </div>
                <div className="stage-grid">
                  {stages.map((stage) => (
                    <div className="stage-card" key={stage.number}>
                      <div className="stage-header">
                        <span>{stage.number} / 04</span>
                        <stage.icon size={21} />
                      </div>
                      <div className="stage-content">
                        <Tag tone={stage.state === 'First gate' ? 'amber' : 'neutral'}>
                          {stage.state}
                        </Tag>
                        <h3>{stage.title}</h3>
                        <p>{stage.body}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              <section className="principle-banner">
                <div className="principle-symbol">
                  <span />
                </div>
                <div>
                  <div className="kicker">OUR STANDARD</div>
                  <h2>
                    A map mark is a clue.
                    <br />A field visit is a confirmation.
                  </h2>
                  <p>
                    Ghost Wells is a research tool for qualified review. It does not issue
                    safety warnings or publish exact possible well locations.
                  </p>
                </div>
                <ArrowDownRight size={27} />
              </section>
            </>
          )}

          {view === 'survey' && (
            <section className="inner-page">
              <div className="page-heading">
                <div className="kicker">STAGE 00 / SOURCE VERIFICATION</div>
                <h1>
                  Ohio sheet survey<span className="heading-period">.</span>
                </h1>
                <p>
                  A working inventory of pilot quadrangles to inspect. A queued sheet is a
                  research target, not proof that its maps contain well symbols.
                </p>
              </div>
              <div className="notice-line">
                <FileSearch size={18} />
                <span>
                  <strong>0 of 6 reviewed.</strong> Counts stay blank until source scans
                  and symbol crops are checked.
                </span>
              </div>
              <div className="table-panel">
                <div className="table-toolbar">
                  <div>
                    <h2>Sheet inventory</h2>
                    <p>Initial survey targets from the project brief</p>
                  </div>
                  <div className="toolbar-actions">
                    <label className="search-box">
                      <Search size={17} />
                      <input
                        aria-label="Search sheets"
                        placeholder="Search sheets"
                        value={query}
                        onChange={(event) => setQuery(event.target.value)}
                      />
                    </label>
                    <label className="filter-box">
                      <SlidersHorizontal size={17} />
                      <select
                        aria-label="Filter by status"
                        value={statusFilter}
                        onChange={(event) => setStatusFilter(event.target.value)}
                      >
                        <option>All statuses</option>
                        <option>Queued</option>
                        <option>Needs review</option>
                        <option>Reviewed</option>
                      </select>
                      <ChevronDown size={15} />
                    </label>
                  </div>
                </div>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>QUADRANGLE</th>
                        <th>COUNTY</th>
                        <th>EDITION</th>
                        <th>STATUS</th>
                        <th>SYMBOLS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.map((sheet) => (
                        <tr key={sheet.name}>
                          <td>
                            <span className="sheet-icon">
                              <Layers3 size={17} />
                            </span>
                            <strong>{sheet.name}</strong>
                          </td>
                          <td>{sheet.county}</td>
                          <td>{sheet.edition}</td>
                          <td>
                            <Tag>{sheet.status}</Tag>
                          </td>
                          <td className="mono">{sheet.symbols}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {filtered.length === 0 && (
                    <div className="empty-state">No sheets match this filter.</div>
                  )}
                </div>
              </div>
              <div className="info-grid">
                <div className="info-card">
                  <div className="info-icon">
                    <Check size={19} />
                  </div>
                  <h3>What counts as reviewed?</h3>
                  <p>
                    A named edition with its source link, year, map crop, and a human
                    check of both symbols and lookalikes.
                  </p>
                </div>
                <div className="info-card">
                  <div className="info-icon">
                    <Download size={19} />
                  </div>
                  <h3>Repeatable by design</h3>
                  <p>
                    The repository includes a CSV survey schema and a command that builds
                    an aggregate report from reviewed rows.
                  </p>
                  <a
                    href="https://github.com/janareddyc7/Ghost-Wells"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open source repository <ArrowUpRight size={15} />
                  </a>
                </div>
              </div>
            </section>
          )}

          {view === 'pipeline' && (
            <section className="inner-page">
              <div className="page-heading">
                <div className="kicker">RESEARCH METHOD</div>
                <h1>
                  One careful step
                  <br />
                  at a time<span className="heading-period">.</span>
                </h1>
                <p>
                  The pipeline moves from historical evidence to private review. Each
                  stage has its own test before the next one can claim results.
                </p>
              </div>
              <div className="pipeline-list">
                {stages.map((stage) => (
                  <article className="pipeline-row" key={stage.number}>
                    <div className="pipeline-index">{stage.number}</div>
                    <div className="pipeline-icon">
                      <stage.icon size={26} />
                    </div>
                    <div>
                      <Tag tone={stage.state === 'First gate' ? 'amber' : 'neutral'}>
                        {stage.state}
                      </Tag>
                      <h2>{stage.title}</h2>
                      <p>{stage.body}</p>
                    </div>
                    <ArrowUpRight className="pipeline-arrow" size={20} />
                  </article>
                ))}
              </div>
              <div className="method-note">
                <div>
                  <div className="kicker">WHY THIS ORDER?</div>
                  <h2>Evidence sets the pace.</h2>
                </div>
                <p>
                  The published AI approach has promising results elsewhere. Its
                  performance on Ohio maps, the number of usable symbols here, and the
                  quality of unmatched leads still need direct measurement.
                </p>
              </div>
            </section>
          )}

          {view === 'about' && (
            <section className="inner-page">
              <div className="page-heading">
                <div className="kicker">ABOUT GHOST WELLS</div>
                <h1>
                  Making old evidence
                  <br />
                  useful again<span className="heading-period">.</span>
                </h1>
                <p>
                  Ohio’s drilling history spans generations. Ghost Wells investigates
                  whether historical maps contain clues that can help qualified reviewers
                  locate wells missing from modern records.
                </p>
              </div>
              <div className="about-grid">
                <div className="about-lead">
                  <div className="kicker">THE IDEA</div>
                  <h2>
                    Read the past.
                    <br />
                    Check the present.
                  </h2>
                  <p>
                    Historical maps may show individual oil and gas well symbols. Computer
                    vision can help find them at scale. Each possible symbol must be
                    traced to its source sheet, checked against official records, and
                    reviewed by a human.
                  </p>
                </div>
                <div className="about-aside">
                  <div>
                    <span>01</span>
                    <h3>Evidence first</h3>
                    <p>
                      Map editions, source crops, and review decisions travel with each
                      lead.
                    </p>
                  </div>
                  <div>
                    <span>02</span>
                    <h3>Privacy by default</h3>
                    <p>
                      Exact possible well coordinates belong in a restricted reviewer
                      workflow.
                    </p>
                  </div>
                  <div>
                    <span>03</span>
                    <h3>Honest uncertainty</h3>
                    <p>
                      Potential leads are never presented as confirmed wells or danger
                      scores.
                    </p>
                  </div>
                </div>
              </div>
              <div className="principle-banner about-banner">
                <div className="principle-symbol">
                  <span />
                </div>
                <div>
                  <div className="kicker">INDEPENDENT PROJECT</div>
                  <h2>Built for careful review.</h2>
                  <p>
                    Ghost Wells is not affiliated with ODNR. Only the appropriate agency
                    can verify a well in the field. Never approach or dig at a possible
                    location.
                  </p>
                </div>
              </div>
            </section>
          )}
        </main>
        <footer>
          <span>© 2026 GHOST WELLS</span>
          <span>OHIO / HISTORICAL MAP RESEARCH</span>
          <button onClick={() => navigate('about')}>
            RESEARCH & SAFETY <ArrowUpRight size={13} />
          </button>
        </footer>
      </div>
      {menuOpen && (
        <button
          className="menu-scrim"
          aria-label="Close menu"
          onClick={() => setMenuOpen(false)}
        />
      )}
    </div>
  )
}

export default App
