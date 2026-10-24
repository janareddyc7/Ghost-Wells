import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Download,
  FolderOpen,
  ShieldCheck,
} from 'lucide-react'

type QueueRow = {
  candidate_id: string
  source_id: string
  sheet: string
  page_x: string
  page_y: string
  mask_area_pixels: string
  crop_path: string
  crop_sha256: string
  batch_file: string
  batch_cell: string
}

type ReviewChoice = 'symbol_candidate' | 'lookalike' | 'uncertain'

type SavedDecision = {
  choice: ReviewChoice
  decided_at_utc: string
  note?: string
}

type QueueItem = QueueRow & {
  cropFile: File
  batchFile: File
  expectedBatchSha256: string
}

type BatchManifest = {
  status?: unknown
  pending_candidate_count?: unknown
  crop_size_pixels?: unknown
  grid?: { columns?: unknown; rows?: unknown; capacity?: unknown }
  batches?: unknown
  contact_sheet_sha256?: unknown
}

type DirectoryFile = File & { webkitRelativePath?: string }

const STORAGE_PREFIX = 'ghost-wells-independent-candidate-review-v1'
const choices: { value: ReviewChoice; title: string; shortcut: string }[] = [
  { value: 'symbol_candidate', title: 'Well-symbol candidate', shortcut: 'S' },
  { value: 'lookalike', title: 'Lookalike / not the target', shortcut: 'R' },
  { value: 'uncertain', title: 'Uncertain', shortcut: 'U' },
]

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
  if (quoted) throw new Error('The review queue CSV has an unclosed quoted field.')
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

function findFile(files: File[], suffix: string): File | undefined {
  return files.find(
    (file) => relativePath(file).endsWith(`/${suffix}`) || file.name === suffix,
  )
}

export default function CandidateReviewDesk() {
  const folderInput = useRef<HTMLInputElement>(null)
  const verifiedCropHashes = useRef(new Map<string, boolean>())
  const verifiedBatchHashes = useRef(new Map<string, string>())
  const [items, setItems] = useState<QueueItem[]>([])
  const [decisions, setDecisions] = useState<Record<string, SavedDecision>>({})
  const [queueSha256, setQueueSha256] = useState('')
  const [batchManifestSha256, setBatchManifestSha256] = useState('')
  const [manifest, setManifest] = useState<BatchManifest | null>(null)
  const [index, setIndex] = useState(0)
  const [reviewerId, setReviewerId] = useState('')
  const [reviewNote, setReviewNote] = useState('')
  const [independenceAttested, setIndependenceAttested] = useState(false)
  const [integrity, setIntegrity] = useState<
    'unloaded' | 'checking' | 'verified' | 'failed'
  >('unloaded')
  const [notice, setNotice] = useState('')

  const current = items[index]
  const cropUrl = useMemo(
    () => (current ? URL.createObjectURL(current.cropFile) : ''),
    [current],
  )
  const batchUrl = useMemo(
    () => (current ? URL.createObjectURL(current.batchFile) : ''),
    [current],
  )
  const reviewedCount = items.reduce(
    (count, item) => count + Number(Boolean(decisions[item.candidate_id])),
    0,
  )
  const remainingCount = items.length - reviewedCount
  const currentCandidateId = current?.candidate_id

  useEffect(() => {
    folderInput.current?.setAttribute('webkitdirectory', '')
  }, [])

  useEffect(() => {
    return () => {
      if (cropUrl) URL.revokeObjectURL(cropUrl)
      if (batchUrl) URL.revokeObjectURL(batchUrl)
    }
  }, [batchUrl, cropUrl])

  useEffect(() => {
    if (!current) {
      setIntegrity('unloaded')
      return
    }
    let active = true
    setIntegrity('checking')
    void (async () => {
      try {
        let valid = verifiedCropHashes.current.get(current.crop_sha256)
        if (valid === undefined) {
          valid = (await sha256(current.cropFile)) === current.crop_sha256
          verifiedCropHashes.current.set(current.crop_sha256, valid)
        }
        const batchKey = `${current.batch_file}:${relativePath(current.batchFile)}`
        if (!verifiedBatchHashes.current.has(batchKey)) {
          const batchHash = await sha256(current.batchFile)
          if (batchHash !== current.expectedBatchSha256) {
            throw new Error(`Contact-sheet hash mismatch for ${current.batch_file}.`)
          }
          verifiedBatchHashes.current.set(batchKey, batchHash)
        }
        if (!active) return
        setIntegrity(valid ? 'verified' : 'failed')
        setNotice(
          valid
            ? ''
            : `Crop hash mismatch for ${current.candidate_id}; this item is locked.`,
        )
      } catch {
        if (!active) return
        setIntegrity('failed')
        setNotice(
          'Could not verify this crop in the browser. Reload the original review folder.',
        )
      }
    })()
    return () => {
      active = false
    }
  }, [current])

  useEffect(() => {
    if (!queueSha256) return
    try {
      localStorage.setItem(
        `${STORAGE_PREFIX}:${queueSha256}`,
        JSON.stringify({ reviewerId, decisions }),
      )
    } catch {
      setNotice('Browser storage is full. Export your review before continuing.')
    }
  }, [decisions, queueSha256, reviewerId])

  useEffect(() => {
    setReviewNote(currentCandidateId ? (decisions[currentCandidateId]?.note ?? '') : '')
  }, [currentCandidateId, decisions])

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLTextAreaElement
      )
        return
      if (event.key === 'ArrowLeft') setIndex((value) => Math.max(0, value - 1))
      if (event.key === 'ArrowRight')
        setIndex((value) => Math.min(items.length - 1, value + 1))
      const choice = choices.find(
        (item) => item.shortcut.toLowerCase() === event.key.toLowerCase(),
      )
      if (choice && current && integrity === 'verified') recordDecision(choice.value)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  })

  function recordDecision(choice: ReviewChoice) {
    if (!current || integrity !== 'verified') return
    setDecisions((previous) => ({
      ...previous,
      [current.candidate_id]: {
        choice,
        decided_at_utc: new Date().toISOString(),
        note: reviewNote.trim(),
      },
    }))
    setNotice('')
    if (index < items.length - 1) setIndex(index + 1)
  }

  async function loadFolder(fileList: FileList | null) {
    if (!fileList) return
    setNotice('Checking queue, contact sheets, and crop files…')
    try {
      const files = Array.from(fileList)
      const queueFile = findFile(files, 'review_queue.csv')
      const manifestFile = findFile(files, 'batch_manifest.json')
      if (!queueFile || !manifestFile) {
        throw new Error(
          'Choose the complete candidate-review folder with its queue, manifest, crops, and contact sheets.',
        )
      }

      const parsedManifest = JSON.parse(await manifestFile.text()) as BatchManifest
      if (parsedManifest.status !== 'pending_visual_review') {
        throw new Error('This folder is not a pending candidate-review batch.')
      }
      if (
        !Array.isArray(parsedManifest.batches) ||
        !parsedManifest.contact_sheet_sha256 ||
        typeof parsedManifest.contact_sheet_sha256 !== 'object'
      ) {
        throw new Error('The batch manifest is missing contact-sheet integrity hashes.')
      }
      const declaredBatchNames = [...parsedManifest.batches].sort()
      const declaredHashNames = Object.keys(parsedManifest.contact_sheet_sha256).sort()
      if (
        declaredBatchNames.length !== declaredHashNames.length ||
        declaredBatchNames.some((name, position) => name !== declaredHashNames[position])
      ) {
        throw new Error('The batch manifest contact-sheet hash list is inconsistent.')
      }
      const table = parseCsv(await queueFile.text())
      if (table.length < 2) throw new Error('The candidate review queue has no rows.')
      const headers = table[0]
      if (!headers) throw new Error('The review queue is missing its header row.')
      const required = [
        'candidate_id',
        'source_id',
        'sheet',
        'page_x',
        'page_y',
        'mask_area_pixels',
        'crop_path',
        'crop_sha256',
        'batch_file',
        'batch_cell',
      ]
      const columns: Record<string, number> = {}
      for (const name of required) columns[name] = headers.indexOf(name)
      if (Object.values(columns).some((column) => column < 0)) {
        throw new Error('The review queue is missing required columns.')
      }

      const fileByRelativePath = new Map(files.map((file) => [relativePath(file), file]))
      const fileByName = new Map(files.map((file) => [file.name, file]))
      const seenIds = new Set<string>()
      const loadedItems = table.slice(1).map((cells) => {
        const row = Object.fromEntries(
          required.map((name) => [name, cells[columns[name] ?? -1] ?? '']),
        ) as QueueRow
        if (!row.candidate_id || seenIds.has(row.candidate_id)) {
          throw new Error(`Missing or duplicate candidate ID: ${row.candidate_id}`)
        }
        seenIds.add(row.candidate_id)
        const cropSuffix = `/${row.crop_path.replaceAll('\\', '/')}`
        const cropFile = [...fileByRelativePath.entries()].find(([path]) =>
          path.endsWith(cropSuffix),
        )?.[1]
        const batchFile = fileByName.get(row.batch_file)
        const expectedBatchSha256 = (
          parsedManifest.contact_sheet_sha256 as Record<string, unknown>
        )[row.batch_file]
        if (
          !cropFile ||
          !batchFile ||
          typeof expectedBatchSha256 !== 'string' ||
          !/^[a-f0-9]{64}$/.test(expectedBatchSha256)
        ) {
          throw new Error(
            `Missing crop, contact sheet, or contact-sheet hash for ${row.candidate_id}. Load the entire folder.`,
          )
        }
        return { ...row, cropFile, batchFile, expectedBatchSha256 }
      })
      if (parsedManifest.pending_candidate_count !== loadedItems.length) {
        throw new Error('Queue row count does not match the batch manifest.')
      }

      const queueDigest = await sha256(queueFile)
      const batchDigest = await sha256(manifestFile)
      let restoredDecisions: Record<string, SavedDecision> = {}
      let restoredReviewer = ''
      try {
        const saved = JSON.parse(
          localStorage.getItem(`${STORAGE_PREFIX}:${queueDigest}`) ?? 'null',
        ) as { reviewerId?: unknown; decisions?: unknown } | null
        if (
          saved &&
          typeof saved.reviewerId === 'string' &&
          saved.decisions &&
          typeof saved.decisions === 'object'
        ) {
          restoredReviewer = saved.reviewerId
          restoredDecisions = saved.decisions as Record<string, SavedDecision>
        }
      } catch {
        restoredDecisions = {}
      }

      verifiedCropHashes.current.clear()
      verifiedBatchHashes.current.clear()
      setItems(loadedItems)
      setManifest(parsedManifest)
      setQueueSha256(queueDigest)
      setBatchManifestSha256(batchDigest)
      setDecisions(restoredDecisions)
      setReviewerId(restoredReviewer)
      setIndependenceAttested(false)
      const firstPending = loadedItems.findIndex(
        (item) => !restoredDecisions[item.candidate_id],
      )
      setIndex(firstPending >= 0 ? firstPending : 0)
      setNotice(
        `Loaded ${loadedItems.length} candidates. Prior AI decisions are hidden from this review.`,
      )
    } catch (error) {
      setNotice(
        error instanceof Error
          ? error.message
          : 'Could not load this candidate-review folder.',
      )
    }
  }

  async function exportReview() {
    if (!items.length || !reviewerId.trim() || !independenceAttested) return
    const batchHashes: Record<string, string> = {}
    try {
      for (const item of items) {
        if (!batchHashes[item.batch_file]) {
          const cacheKey = `${item.batch_file}:${relativePath(item.batchFile)}`
          const actualHash =
            verifiedBatchHashes.current.get(cacheKey) ?? (await sha256(item.batchFile))
          if (actualHash !== item.expectedBatchSha256) {
            throw new Error(`Contact-sheet hash mismatch for ${item.batch_file}.`)
          }
          batchHashes[item.batch_file] = actualHash
        }
      }
      const payload = {
        schema_version: 1,
        review_type: 'independent_blind_candidate_adjudication',
        reviewer_id: reviewerId.trim(),
        exported_at_utc: new Date().toISOString(),
        independent_of_ai_screen_attested: true,
        all_queued_candidates_reviewed: reviewedCount === items.length,
        reviewed_count: reviewedCount,
        pending_count: remainingCount,
        queue_sha256: queueSha256,
        batch_manifest_sha256: batchManifestSha256,
        contact_sheet_sha256: batchHashes,
        decisions: items.map((item) => ({
          candidate_id: item.candidate_id,
          source_id: item.source_id,
          sheet: item.sheet,
          decision: decisions[item.candidate_id]?.choice ?? 'pending',
          decided_at_utc: decisions[item.candidate_id]?.decided_at_utc ?? null,
          review_note: decisions[item.candidate_id]?.note ?? '',
          crop_sha256: item.crop_sha256,
          contact_sheet: item.batch_file,
          contact_sheet_cell: Number(item.batch_cell),
        })),
        note: 'Visual map-symbol adjudication only. This does not confirm a physical well or establish a ground location.',
      }
      const blobUrl = URL.createObjectURL(
        new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }),
      )
      const anchor = document.createElement('a')
      anchor.href = blobUrl
      anchor.download = 'ghost-wells-independent-review.json'
      anchor.click()
      URL.revokeObjectURL(blobUrl)
      setNotice(
        'Independent-review export downloaded. Keep it private with the source map data.',
      )
    } catch {
      setNotice(
        'Could not prepare the review export. Browser storage remains available for this queue.',
      )
    }
  }

  const gridColumns = Number(manifest?.grid?.columns ?? 4)
  const gridRows = Number(manifest?.grid?.rows ?? 4)
  const cropSize = Number(manifest?.crop_size_pixels ?? 256)
  const cellWidth = cropSize + 20
  const cellHeight = cropSize + 42
  const cellNumber = Number(current?.batch_cell ?? 1) - 1

  return (
    <section
      className="candidate-review-desk"
      aria-label="Independent candidate review workspace"
    >
      <div className="candidate-review-heading">
        <div>
          <div className="kicker">PRIVATE · LOCAL-ONLY ADJUDICATION</div>
          <h2>Second-review the candidate crops.</h2>
          <p>
            This desk hides the first-pass AI labels. Review the source crop in its
            contact-sheet context; decisions stay in this browser until you export them.
          </p>
        </div>
        <button className="button-primary" onClick={() => folderInput.current?.click()}>
          <FolderOpen size={17} /> Load review folder
        </button>
        <input
          ref={folderInput}
          className="visually-hidden"
          type="file"
          multiple
          onChange={(event) => void loadFolder(event.target.files)}
          aria-label="Choose complete private candidate review folder"
        />
      </div>

      <div className="candidate-review-stats">
        <span>
          <strong>{items.length}</strong> candidates loaded
        </span>
        <span>
          <strong>{reviewedCount}</strong> reviewed
        </span>
        <span>
          <strong>{remainingCount}</strong> remaining
        </span>
        <span className={`candidate-integrity integrity-${integrity}`}>
          <ShieldCheck size={14} />{' '}
          {integrity === 'verified'
            ? 'Crop hash verified'
            : integrity === 'checking'
              ? 'Checking crop…'
              : integrity === 'failed'
                ? 'Crop integrity error'
                : 'Load a queue to begin'}
        </span>
        <label className="candidate-reviewer-field">
          Reviewer ID
          <input
            value={reviewerId}
            onChange={(event) => setReviewerId(event.target.value)}
            placeholder="Your reviewer ID"
          />
        </label>
        <button
          className="inline-link"
          onClick={() => void exportReview()}
          disabled={
            !items.length ||
            !reviewerId.trim() ||
            !independenceAttested ||
            reviewedCount === 0
          }
        >
          <Download size={16} /> Export review
        </button>
      </div>

      {items.length > 0 && current ? (
        <>
          <div className="candidate-review-toolbar">
            <span>
              <strong>{current.candidate_id}</strong> · {current.sheet} · {index + 1} /{' '}
              {items.length}
            </span>
            <span>
              {decisions[current.candidate_id]
                ? `Saved: ${decisions[current.candidate_id]?.choice}`
                : 'Awaiting independent decision'}
            </span>
          </div>
          <div className="candidate-review-visuals">
            <div className="candidate-contact-panel">
              <div className="candidate-visual-label">
                CONTACT SHEET · RED CROSSHAIR SHOWS TARGET
              </div>
              <div className="candidate-contact-image">
                <img src={batchUrl} alt={`Contact sheet ${current.batch_file}`} />
                <svg
                  viewBox={`0 0 ${gridColumns * cellWidth} ${gridRows * cellHeight}`}
                  aria-hidden="true"
                >
                  <rect
                    x={(cellNumber % gridColumns) * cellWidth + 8}
                    y={Math.floor(cellNumber / gridColumns) * cellHeight + 16}
                    width={cropSize + 4}
                    height={cropSize + 4}
                    rx="3"
                  />
                </svg>
              </div>
            </div>
            <div className="candidate-crop-panel">
              <div className="candidate-visual-label">
                SOURCE CROP · {current.mask_area_pixels} PIXEL COMPONENT
              </div>
              <img src={cropUrl} alt={`Candidate map crop ${current.candidate_id}`} />
              <p>
                Rendered-page pixel center: {current.page_x}, {current.page_y}. Not
                geographic coordinates.
              </p>
            </div>
          </div>
          <label className="candidate-review-note">
            Review note{' '}
            <span>(optional; useful for uncertain or lookalike decisions)</span>
            <textarea
              value={reviewNote}
              onChange={(event) => setReviewNote(event.target.value)}
              placeholder="What map detail informed this decision?"
              rows={2}
            />
          </label>
          <div
            className="candidate-review-actions"
            role="group"
            aria-label="Independent review decision"
          >
            <button
              className="button-secondary"
              onClick={() => setIndex(Math.max(0, index - 1))}
              disabled={index === 0}
            >
              <ChevronLeft size={15} /> Previous
            </button>
            {choices.map((choice) => (
              <button
                className={`candidate-choice ${decisions[current.candidate_id]?.choice === choice.value ? 'selected' : ''}`}
                key={choice.value}
                onClick={() => recordDecision(choice.value)}
                disabled={integrity !== 'verified'}
              >
                {decisions[current.candidate_id]?.choice === choice.value && (
                  <Check size={15} />
                )}
                {choice.title} <kbd>{choice.shortcut}</kbd>
              </button>
            ))}
            <button
              className="button-secondary"
              onClick={() => setIndex(Math.min(items.length - 1, index + 1))}
              disabled={index >= items.length - 1}
            >
              Next <ChevronRight size={15} />
            </button>
          </div>
          <label className="candidate-independence-attestation">
            <input
              type="checkbox"
              checked={independenceAttested}
              onChange={(event) => setIndependenceAttested(event.target.checked)}
            />
            I am a separate reviewer and assigned these labels without seeing the AI’s
            prior decisions.
          </label>
        </>
      ) : (
        <div className="candidate-review-empty">
          <FolderOpen size={28} />
          <strong>No candidate queue loaded</strong>
          <p>
            Select the complete <code>candidate-review-all-v4</code> folder, including{' '}
            <code>review_queue.csv</code>, <code>batch_manifest.json</code>,{' '}
            <code>crops/</code>, and contact sheets.
          </p>
        </div>
      )}
      {notice && (
        <p className="candidate-review-notice" role="status">
          {notice}
        </p>
      )}
      <p className="candidate-review-footnote">
        Keep the review folder, browser export, exact pixel positions, and source scans
        private. A symbol decision is not proof that a physical well exists.
      </p>
    </section>
  )
}
