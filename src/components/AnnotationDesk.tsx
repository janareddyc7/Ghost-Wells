import { useEffect, useMemo, useRef, useState } from 'react'
import type { MouseEvent } from 'react'
import { Download, FolderOpen, Undo2 } from 'lucide-react'
import pilot from '../../evidence/pilot_sheets.json'

type Label =
  | 'well_symbol'
  | 'benchmark'
  | 'tank'
  | 'windmill'
  | 'spot_elevation'
  | 'other_lookalike'
  | 'uncertain'

type Chip = {
  file: File
  sourceId: string
  pageX: number
  pageY: number
  scale: number
}

type Mark = {
  id: string
  chip: string
  sourceId: string
  pageX: number
  pageY: number
  renderScale: number
  label: Label
  createdAt: string
}

type ReviewState = {
  reviewer: string
  marks: Mark[]
  reviewed: string[]
  blindToModelCandidates: boolean
}

const STORAGE_KEY = 'ghost-wells-local-review-v1'
const labels: { key: Label; title: string; keyHint: string; color: string }[] = [
  { key: 'well_symbol', title: 'Oil / gas well', keyHint: '1', color: '#d66a3a' },
  { key: 'benchmark', title: 'Benchmark', keyHint: '2', color: '#3c74ad' },
  { key: 'tank', title: 'Tank / tank farm', keyHint: '3', color: '#9060a5' },
  { key: 'windmill', title: 'Windmill', keyHint: '4', color: '#59926f' },
  { key: 'spot_elevation', title: 'Spot elevation', keyHint: '5', color: '#b79b31' },
  { key: 'other_lookalike', title: 'Other lookalike', keyHint: '6', color: '#68747a' },
  { key: 'uncertain', title: 'Uncertain', keyHint: '7', color: '#bd4a71' },
]

function readSavedState(): ReviewState {
  try {
    const parsed = JSON.parse(
      localStorage.getItem(STORAGE_KEY) ?? '{}',
    ) as Partial<ReviewState>
    return {
      reviewer: typeof parsed.reviewer === 'string' ? parsed.reviewer : '',
      marks: Array.isArray(parsed.marks) ? parsed.marks : [],
      reviewed: Array.isArray(parsed.reviewed) ? parsed.reviewed : [],
      blindToModelCandidates: parsed.blindToModelCandidates === true,
    }
  } catch {
    return { reviewer: '', marks: [], reviewed: [], blindToModelCandidates: false }
  }
}

export default function AnnotationDesk() {
  const folderInput = useRef<HTMLInputElement>(null)
  const imageRef = useRef<HTMLImageElement>(null)
  const [chips, setChips] = useState<Chip[]>([])
  const [index, setIndex] = useState(0)
  const [label, setLabel] = useState<Label>('well_symbol')
  const [review, setReview] = useState<ReviewState>(() => readSavedState())
  const [imageSize, setImageSize] = useState({ width: 0, height: 0 })
  const [notice, setNotice] = useState('')
  const [expectedChipCount, setExpectedChipCount] = useState<number | null>(null)

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(review))
    } catch {
      setNotice('Browser storage is full. Export the annotations before continuing.')
    }
  }, [review])
  useEffect(() => {
    folderInput.current?.setAttribute('webkitdirectory', '')
  }, [])

  const chip = chips[index]
  const loadedNames = new Set(chips.map((item) => item.file.name))
  const objectUrl = useMemo(() => (chip ? URL.createObjectURL(chip.file) : ''), [chip])
  useEffect(() => {
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [objectUrl])
  const currentMarks = chip
    ? review.marks.filter((mark) => mark.chip === chip.file.name)
    : []
  const markedWells = review.marks.filter(
    (mark) => mark.label === 'well_symbol' && loadedNames.has(mark.chip),
  ).length
  const completed = review.reviewed.filter((name) => loadedNames.has(name)).length

  async function loadFolder(files: FileList | null) {
    if (!files) return
    const selected = Array.from(files)
    const queueFile = selected.find((file) => file.name === 'review_queue.json')
    if (queueFile) {
      try {
        const queue = (await queueFile.text()) as string
        const parsed = JSON.parse(queue) as { chip_count?: unknown }
        setExpectedChipCount(
          typeof parsed.chip_count === 'number' ? parsed.chip_count : null,
        )
      } catch {
        setExpectedChipCount(null)
      }
    } else {
      setExpectedChipCount(null)
    }
    const loaded: Chip[] = selected
      .filter((file) => file.name.toLowerCase().endsWith('.jpg'))
      .flatMap((file) => {
        const match = file.name.match(/^([a-f\d]+)__s(\d+)__x(\d+)_y(\d+)\.jpg$/i)
        if (!match) return []
        const sourceId = match[1]
        const scale = match[2]
        const pageX = match[3]
        const pageY = match[4]
        if (!sourceId || !scale || !pageX || !pageY) return []
        return [
          {
            file,
            sourceId,
            scale: Number(scale) / 1000,
            pageX: Number(pageX),
            pageY: Number(pageY),
          },
        ]
      })
      .sort(
        (a, b) =>
          a.sourceId.localeCompare(b.sourceId) || a.pageY - b.pageY || a.pageX - b.pageX,
      )
    setChips(loaded)
    setIndex(0)
    setImageSize({ width: 0, height: 0 })
  }

  function addMark(event: MouseEvent<SVGSVGElement>) {
    if (!chip || imageSize.width === 0) return
    const bounds = event.currentTarget.getBoundingClientRect()
    const x = ((event.clientX - bounds.left) / bounds.width) * imageSize.width
    const y = ((event.clientY - bounds.top) / bounds.height) * imageSize.height
    const pageX = Math.round(chip.pageX + x)
    const pageY = Math.round(chip.pageY + y)
    const duplicate = review.marks.some(
      (mark) =>
        mark.sourceId === chip.sourceId &&
        Math.hypot(mark.pageX - pageX, mark.pageY - pageY) < 24,
    )
    if (duplicate) {
      setNotice('That map point is already marked in an overlapping tile.')
      return
    }
    setNotice('')
    const mark: Mark = {
      id: crypto.randomUUID(),
      chip: chip.file.name,
      sourceId: chip.sourceId,
      pageX,
      pageY,
      renderScale: chip.scale,
      label,
      createdAt: new Date().toISOString(),
    }
    setReview((previous) => ({ ...previous, marks: [...previous.marks, mark] }))
  }

  function undoMark() {
    if (!chip) return
    const last = [...currentMarks].pop()
    if (!last) return
    setReview((previous) => ({
      ...previous,
      marks: previous.marks.filter((mark) => mark.id !== last.id),
    }))
  }

  function markReviewed() {
    if (!chip) return
    setReview((previous) => ({
      ...previous,
      reviewed: previous.reviewed.includes(chip.file.name)
        ? previous.reviewed
        : [...previous.reviewed, chip.file.name],
    }))
  }

  function exportReview() {
    const sourceIds = [...new Set(chips.map((item) => item.sourceId))]
    const sheets = pilot.sheets.filter((item) => sourceIds.includes(item.source_id))
    const payload = {
      schema_version: 1,
      exported_at_utc: new Date().toISOString(),
      coordinate_space: 'rendered_page_pixels',
      reviewer: review.reviewer,
      review_inventory_blind_to_model_candidates: review.blindToModelCandidates,
      sheets: sheets.map(({ source_id, name, county, year, sha256 }) => ({
        source_id,
        name,
        county,
        year,
        source_sha256: sha256,
      })),
      reviewed_chips: review.reviewed.filter((name) =>
        chips.some((item) => item.file.name === name),
      ),
      unreviewed_chips: chips
        .filter((item) => !review.reviewed.includes(item.file.name))
        .map((item) => item.file.name),
      marks: review.marks.filter((mark) =>
        chips.some((item) => item.file.name === mark.chip),
      ),
      note: 'Research annotations only. Pixel positions are not ground coordinates or confirmed wells.',
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: 'application/json',
    })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = 'ghost-wells-review-annotations.json'
    link.click()
    URL.revokeObjectURL(link.href)
  }

  function advance(delta: number) {
    setIndex((previous) => Math.max(0, Math.min(chips.length - 1, previous + delta)))
    setImageSize({ width: 0, height: 0 })
  }

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLTextAreaElement
      )
        return
      const shortcut = labels.find((item) => item.keyHint === event.key)
      if (shortcut) setLabel(shortcut.key)
      if (event.key === 'Backspace') {
        event.preventDefault()
        undoMark()
      }
      if (event.key === 'ArrowRight') advance(1)
      if (event.key === 'ArrowLeft') advance(-1)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  })

  return (
    <section className="annotation-desk" aria-label="Local symbol annotation workspace">
      <div className="annotation-heading">
        <div>
          <div className="kicker">LOCAL REVIEW WORKSPACE</div>
          <h2>Mark what the map shows.</h2>
          <p>
            Annotations stay in this browser until you export them. Choose the generated
            tile folder to begin.
          </p>
        </div>
        <button className="button-primary" onClick={() => folderInput.current?.click()}>
          <FolderOpen size={17} /> Load tile folder
        </button>
        <input
          ref={folderInput}
          className="visually-hidden"
          type="file"
          multiple
          onChange={(event) => loadFolder(event.target.files)}
          aria-label="Choose generated map tile folder"
        />
      </div>

      <div className="annotation-stats">
        <span>
          <strong>
            {chips.length}
            {expectedChipCount !== null ? ` / ${expectedChipCount}` : ''}
          </strong>{' '}
          chips loaded
        </span>
        <span>
          <strong>{completed}</strong> marked reviewed
        </span>
        <span>
          <strong>{markedWells}</strong> well labels placed
        </span>
        <label className="reviewer-field">
          Reviewer ID{' '}
          <input
            value={review.reviewer}
            onChange={(event) =>
              setReview((previous) => ({ ...previous, reviewer: event.target.value }))
            }
            placeholder="Required before export"
          />
        </label>
        <label className="reviewer-field">
          <input
            type="checkbox"
            checked={review.blindToModelCandidates}
            onChange={(event) =>
              setReview((previous) => ({
                ...previous,
                blindToModelCandidates: event.target.checked,
              }))
            }
          />
          Map inventory was reviewed without viewing detector candidates
        </label>
        <button
          className="inline-link"
          onClick={exportReview}
          disabled={chips.length === 0 || review.reviewer.trim().length === 0}
        >
          <Download size={16} /> Export annotations
        </button>
      </div>

      <div className="annotation-layout">
        <div className="annotation-labels" role="group" aria-label="Annotation class">
          {labels.map((item) => (
            <button
              key={item.key}
              className={`annotation-label ${label === item.key ? 'selected' : ''}`}
              onClick={() => setLabel(item.key)}
              aria-pressed={label === item.key}
            >
              <i style={{ backgroundColor: item.color }} />
              <span>{item.title}</span>
              <kbd>{item.keyHint}</kbd>
            </button>
          ))}
          <p>
            Click the center of each symbol inside the map border. Skip collar text,
            legends, and duplicated overlap symbols.
          </p>
        </div>

        <div className="annotation-viewer">
          {chip ? (
            <>
              <div className="annotation-viewer-toolbar">
                <span>{chip.file.name}</span>
                <span>
                  {index + 1} / {chips.length} ·{' '}
                  {review.reviewed.includes(chip.file.name) ? 'reviewed' : 'pending'}
                </span>
              </div>
              <div className="annotation-image-wrap">
                <div className="annotation-canvas">
                  <img
                    ref={imageRef}
                    src={objectUrl}
                    alt={`Historical map tile ${chip.file.name}`}
                    onLoad={(event) =>
                      setImageSize({
                        width: event.currentTarget.naturalWidth,
                        height: event.currentTarget.naturalHeight,
                      })
                    }
                  />
                  <svg
                    className="annotation-overlay"
                    viewBox={`0 0 ${imageSize.width || 1} ${imageSize.height || 1}`}
                    onClick={addMark}
                    role="presentation"
                  >
                    {currentMarks.map((mark) => {
                      const style = labels.find((item) => item.key === mark.label)
                      const localX = mark.pageX - chip.pageX
                      const localY = mark.pageY - chip.pageY
                      return (
                        <circle
                          key={mark.id}
                          cx={localX}
                          cy={localY}
                          r={10}
                          fill="none"
                          stroke={style?.color ?? '#d66a3a'}
                          strokeWidth={3}
                          vectorEffect="non-scaling-stroke"
                        />
                      )
                    })}
                  </svg>
                </div>
              </div>
              <div className="annotation-viewer-footer">
                <button
                  className="button-secondary"
                  onClick={() => advance(-1)}
                  disabled={index === 0}
                >
                  Previous
                </button>
                <button
                  className="button-secondary"
                  onClick={undoMark}
                  disabled={currentMarks.length === 0}
                >
                  <Undo2 size={15} /> Undo mark
                </button>
                <button className="button-secondary" onClick={markReviewed}>
                  {review.reviewed.includes(chip.file.name)
                    ? 'Tile reviewed'
                    : 'Mark tile reviewed'}
                </button>
                <button
                  className="button-secondary"
                  onClick={() => advance(1)}
                  disabled={index >= chips.length - 1}
                >
                  Next tile
                </button>
                <button
                  className="button-secondary"
                  onClick={() => {
                    const nextPending = chips.findIndex(
                      (item, itemIndex) =>
                        itemIndex > index && !review.reviewed.includes(item.file.name),
                    )
                    if (nextPending >= 0) {
                      setIndex(nextPending)
                      setImageSize({ width: 0, height: 0 })
                    }
                  }}
                  disabled={
                    !chips.some(
                      (item, itemIndex) =>
                        itemIndex > index && !review.reviewed.includes(item.file.name),
                    )
                  }
                >
                  Next pending
                </button>
              </div>
            </>
          ) : (
            <div className="annotation-empty">
              <FolderOpen size={32} />
              <strong>No map tiles loaded</strong>
              <p>
                Generate tiles with the command shown below, then load the output folder
                here.
              </p>
              <code>
                python -m ghostwells tiles --manifest evidence/pilot_sheets.json
                --data-dir data/usgs --output-dir data/usgs/tiles
              </code>
            </div>
          )}
        </div>
      </div>
      {notice && (
        <p className="annotation-notice" role="status">
          {notice}
        </p>
      )}
      {expectedChipCount !== null && chips.length !== expectedChipCount && (
        <p className="annotation-notice" role="status">
          Incomplete tile batch: load all {expectedChipCount} chips with their
          review_queue.json before treating this as a complete-sheet review.
        </p>
      )}
      <p className="annotation-footnote">
        The exported coordinates are rendered page pixels. They do not identify a ground
        location by themselves. Keep the export private while it contains marked wells.
      </p>
    </section>
  )
}
