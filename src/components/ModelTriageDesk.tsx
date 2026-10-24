import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, FolderOpen, Search, ShieldCheck } from 'lucide-react'

type PriorityRow = {
  priority_rank: string
  sample_id: string
  candidate_id: string
  source_id: string
  sheet: string
  county: string
  source_review_status: string
  uncalibrated_symbol_rank_score: string
  crop_path: string
  crop_sha256: string
}

type TriageItem = PriorityRow & { cropFile: File }
type DirectoryFile = File & { webkitRelativePath?: string }

type RankerReport = {
  training_scope?: unknown
  dataset_id?: unknown
  uncertain_priority_count?: unknown
  uncertain_priority_csv_sha256?: unknown
  validation_metrics?: unknown
  evaluation_ready?: unknown
  deployment_ready?: unknown
}

type TriageManifest = {
  schema_version?: unknown
  package_type?: unknown
  status?: unknown
  dataset_id?: unknown
  ranker_run_sha256?: unknown
  queue_sha256?: unknown
  crop_count?: unknown
  crop_sha256?: unknown
  evaluation_ready?: unknown
  deployment_ready?: unknown
}

function relativePath(file: File): string {
  return ((file as DirectoryFile).webkitRelativePath || file.name).replaceAll('\\', '/')
}

function parseCsv(input: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let quoted = false

  for (let index = 0; index < input.length; index += 1) {
    const character = input[index]
    if (quoted) {
      if (character === '"' && input[index + 1] === '"') {
        field += '"'
        index += 1
      } else if (character === '"') {
        quoted = false
      } else {
        field += character
      }
    } else if (character === '"' && field.length === 0) {
      quoted = true
    } else if (character === ',') {
      row.push(field)
      field = ''
    } else if (character === '\n' || character === '\r') {
      if (character === '\r' && input[index + 1] === '\n') index += 1
      row.push(field)
      if (row.some((cell) => cell.length > 0)) rows.push(row)
      row = []
      field = ''
    } else {
      field += character
    }
  }
  if (quoted) throw new Error('The model-priority CSV has an unclosed quoted field.')
  row.push(field)
  if (row.some((cell) => cell.length > 0)) rows.push(row)
  return rows
}

async function sha256(file: File): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('')
}

function findFile(files: File[], name: string): File | undefined {
  return files.find(
    (file) => relativePath(file).endsWith(`/${name}`) || file.name === name,
  )
}

function findCrop(files: File[], cropPath: string): File | undefined {
  const suffix = `/${cropPath}`
  return files.find((file) => relativePath(file).endsWith(suffix))
}

export default function ModelTriageDesk() {
  const folderInput = useRef<HTMLInputElement>(null)
  const [items, setItems] = useState<TriageItem[]>([])
  const [index, setIndex] = useState(0)
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(false)
  const [integrityVerified, setIntegrityVerified] = useState(false)

  useEffect(() => {
    folderInput.current?.setAttribute('webkitdirectory', '')
  }, [])

  const filteredItems = useMemo(
    () =>
      items.filter((item) => {
        const matchesQuery =
          `${item.candidate_id} ${item.sheet} ${item.county} ${item.source_id}`
            .toLowerCase()
            .includes(query.toLowerCase())
        return (
          matchesQuery &&
          (statusFilter === 'all' || item.source_review_status === statusFilter)
        )
      }),
    [items, query, statusFilter],
  )
  const current = filteredItems[index]
  const cropUrl = useMemo(
    () => (current ? URL.createObjectURL(current.cropFile) : ''),
    [current],
  )

  useEffect(() => {
    return () => {
      if (cropUrl) URL.revokeObjectURL(cropUrl)
    }
  }, [cropUrl])

  useEffect(() => {
    setIndex(0)
  }, [query, statusFilter])

  async function loadPackage(fileList: FileList | null) {
    if (!fileList) return
    setLoading(true)
    setItems([])
    setIndex(0)
    setIntegrityVerified(false)
    setNotice('Checking package, run report, queue, and crop hashes…')
    try {
      const files = Array.from(fileList)
      const packageFile = findFile(files, 'triage_package.json')
      const reportFile = findFile(files, 'ranker_run.json')
      const queueFile = findFile(files, 'uncertain_crop_priority.csv')
      if (!packageFile || !reportFile || !queueFile) {
        throw new Error(
          'Choose the complete private triage package folder, including its manifest, report, queue, and crops.',
        )
      }

      const manifest = JSON.parse(await packageFile.text()) as TriageManifest
      const report = JSON.parse(await reportFile.text()) as RankerReport
      if (
        manifest.schema_version !== 1 ||
        manifest.package_type !== 'private_local_model_triage_queue' ||
        manifest.status !== 'uncalibrated_rank_only'
      ) {
        throw new Error('This folder is not a supported fit-only model-triage package.')
      }
      if (
        manifest.evaluation_ready !== false ||
        manifest.deployment_ready !== false ||
        report.evaluation_ready !== false ||
        report.deployment_ready !== false ||
        report.validation_metrics !== null
      ) {
        throw new Error(
          'The package must explicitly keep evaluation and deployment disabled.',
        )
      }
      if (
        report.training_scope !==
          'frozen_imagenet_embedding_weighted_linear_probe_fit_only' ||
        manifest.dataset_id !== report.dataset_id
      ) {
        throw new Error('The triage package and ranker report do not match.')
      }

      const reportHash = await sha256(reportFile)
      const queueHash = await sha256(queueFile)
      if (
        reportHash !== manifest.ranker_run_sha256 ||
        queueHash !== manifest.queue_sha256 ||
        queueHash !== report.uncertain_priority_csv_sha256
      ) {
        throw new Error('A package manifest, run report, or queue hash does not match.')
      }

      const table = parseCsv(await queueFile.text())
      const headers = table[0]
      if (!headers) throw new Error('The ranked queue is empty.')
      const required: (keyof PriorityRow)[] = [
        'priority_rank',
        'sample_id',
        'candidate_id',
        'source_id',
        'sheet',
        'county',
        'source_review_status',
        'uncalibrated_symbol_rank_score',
        'crop_path',
        'crop_sha256',
      ]
      const columns = Object.fromEntries(
        required.map((name) => [name, headers.indexOf(name)]),
      ) as Record<keyof PriorityRow, number>
      if (Object.values(columns).some((column) => column < 0)) {
        throw new Error('The ranked queue is missing a required column.')
      }
      const rows = table.slice(1).map((cells) => {
        const row = Object.fromEntries(
          required.map((name) => [name, cells[columns[name]] ?? '']),
        ) as PriorityRow
        return row
      })
      if (
        !rows.length ||
        rows.length !== manifest.crop_count ||
        rows.length !== report.uncertain_priority_count ||
        !manifest.crop_sha256 ||
        typeof manifest.crop_sha256 !== 'object'
      ) {
        throw new Error(
          'The queue row count does not match its package and run manifests.',
        )
      }

      const cropHashes = manifest.crop_sha256 as Record<string, unknown>
      if (Object.keys(cropHashes).length !== rows.length) {
        throw new Error('The package crop-hash inventory has an unexpected size.')
      }
      const seenIds = new Set<string>()
      const loadedItems = await Promise.all(
        rows.map(async (row, position) => {
          const scoreText = row.uncalibrated_symbol_rank_score
          const score = Number(scoreText)
          const previousScore =
            position > 0
              ? Number(rows[position - 1]?.uncalibrated_symbol_rank_score)
              : Number.POSITIVE_INFINITY
          const expectedPath = `crops/${row.sample_id}.png`
          if (
            !row.sample_id ||
            !/^[A-Za-z0-9_-]+$/.test(row.sample_id) ||
            seenIds.has(row.sample_id) ||
            row.priority_rank !== String(position + 1) ||
            !/^(?:0(?:\.\d+)?|1(?:\.0+)?)$/.test(scoreText) ||
            !Number.isFinite(score) ||
            score < 0 ||
            score > 1 ||
            score > previousScore ||
            ![expectedPath, 'crops/negative_' + row.sample_id + '.png'].includes(
              row.crop_path,
            ) ||
            !['ai_screen_uncertain', 'uncertain'].includes(row.source_review_status)
          ) {
            throw new Error(`Invalid ranked queue row at position ${position + 1}.`)
          }
          seenIds.add(row.sample_id)
          if (cropHashes[row.crop_path] !== row.crop_sha256) {
            throw new Error(`Crop inventory hash mismatch for ${row.sample_id}.`)
          }
          const cropFile = findCrop(files, row.crop_path)
          if (!cropFile || (await sha256(cropFile)) !== row.crop_sha256) {
            throw new Error(`Missing or altered crop for ${row.sample_id}.`)
          }
          return { ...row, cropFile }
        }),
      )

      setItems(loadedItems)
      setIndex(0)
      setIntegrityVerified(true)
      setNotice(
        `Verified ${loadedItems.length} ranked crops locally. No files were uploaded by this view.`,
      )
    } catch (error) {
      setIntegrityVerified(false)
      setNotice(
        error instanceof Error ? error.message : 'Could not load this triage package.',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="inner-page model-triage-page" aria-label="Model triage workspace">
      <div className="page-heading">
        <div className="kicker">PRIVATE · LOCAL MODEL TRIAGE</div>
        <h1>
          Ranked map crops<span className="heading-period">.</span>
        </h1>
        <p>
          Browse the 172 uncertain crops in model-priority order. This is a visual triage
          aid only: scores are uncalibrated, and no crop is verified as a well.
        </p>
      </div>

      <div className="model-triage-disclosure">
        <ShieldCheck size={19} />
        <div>
          <strong>Fit-only model · no independent validation</strong>
          <p>
            The ranker learned from a mix dominated by provisional AI labels. Its score is
            not a probability, accuracy measure, or physical-well confirmation. This queue
            is separate from the blinded human-review desk.
          </p>
        </div>
      </div>

      <div className="model-triage-toolbar">
        <div>
          <strong>{items.length || '—'}</strong> crops loaded
          <span className="model-triage-integrity">
            {integrityVerified ? 'Package and crop hashes verified' : 'No package loaded'}
          </span>
        </div>
        <label className="button-primary model-triage-load">
          <FolderOpen size={17} />{' '}
          {loading ? 'Checking package…' : 'Load private triage package'}
          <input
            ref={folderInput}
            className="visually-hidden"
            type="file"
            multiple
            onChange={(event) => void loadPackage(event.target.files)}
            aria-label="Choose private model triage package folder"
            disabled={loading}
          />
        </label>
      </div>

      {items.length > 0 && (
        <>
          <div className="model-triage-filters">
            <label className="search-box">
              <Search size={17} />
              <input
                aria-label="Search ranked crops"
                placeholder="Search sheet, county, or source"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <label className="filter-box">
              <span className="visually-hidden">Filter by source status</span>
              <select
                aria-label="Filter by source status"
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
              >
                <option value="all">All uncertain crops</option>
                <option value="ai_screen_uncertain">AI screen: uncertain</option>
                <option value="uncertain">Earlier review: uncertain</option>
              </select>
            </label>
          </div>

          {current ? (
            <article className="model-triage-card">
              <div className="model-triage-image-panel">
                <div className="candidate-visual-label">
                  SOURCE CROP · NO DECISION RECORDED
                </div>
                <div className="model-triage-image">
                  <img
                    src={cropUrl}
                    alt={`Historical map crop ${current.candidate_id}`}
                  />
                </div>
              </div>
              <div className="model-triage-details">
                <div className="model-triage-rank">
                  PRIORITY RANK {current.priority_rank} OF {items.length}
                </div>
                <h2>{current.sheet}</h2>
                <p className="model-triage-location">{current.county} County · Ohio</p>
                <dl>
                  <div>
                    <dt>Uncalibrated rank score</dt>
                    <dd>{Number(current.uncalibrated_symbol_rank_score).toFixed(4)}</dd>
                  </div>
                  <div>
                    <dt>Source review status</dt>
                    <dd>
                      {current.source_review_status === 'ai_screen_uncertain'
                        ? 'AI screen: uncertain'
                        : 'Earlier review: uncertain'}
                    </dd>
                  </div>
                  <div>
                    <dt>Candidate ID</dt>
                    <dd className="model-triage-id">{current.candidate_id}</dd>
                  </div>
                </dl>
                <div className="model-triage-navigation">
                  <button
                    className="button-secondary"
                    onClick={() => setIndex(Math.max(0, index - 1))}
                    disabled={index === 0}
                  >
                    <ChevronLeft size={15} /> Previous
                  </button>
                  <span>
                    {index + 1} / {filteredItems.length}
                  </span>
                  <button
                    className="button-secondary"
                    onClick={() =>
                      setIndex(Math.min(filteredItems.length - 1, index + 1))
                    }
                    disabled={index >= filteredItems.length - 1}
                  >
                    Next <ChevronRight size={15} />
                  </button>
                </div>
              </div>
            </article>
          ) : (
            <div className="candidate-review-empty">
              <Search size={25} />
              <strong>No crops match these filters</strong>
              <p>Change the search or source-status filter to see ranked crops.</p>
            </div>
          )}
        </>
      )}

      {!items.length && !loading && (
        <div className="candidate-review-empty model-triage-empty">
          <FolderOpen size={28} />
          <strong>No private triage package loaded</strong>
          <p>
            Load the complete <code>triage-package-v1</code> folder generated by the
            project’s package-export command. The app verifies the run report, queue, and
            each crop before displaying them.
          </p>
        </div>
      )}

      {notice && (
        <p className="candidate-review-notice" role="status">
          {notice}
        </p>
      )}
      <p className="model-triage-footnote">
        Selected files are read in this browser only; this view contains no upload or
        decision-saving behavior. Keep the package private. A ranked visual match is not
        evidence that a physical well remains at the location.
      </p>
    </section>
  )
}
