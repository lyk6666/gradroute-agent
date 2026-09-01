'use client';

import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  BookOpenCheck,
  BriefcaseBusiness,
  ChevronLeft,
  ChevronRight,
  Database,
  FileCheck2,
  GraduationCap,
  Link2,
  LockKeyhole,
  RefreshCw,
  Search,
  ShieldCheck,
  Users,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { AppShell } from '@/components/shell/AppShell';
import {
  fetchDataCatalog,
  fetchDataPage,
  type DataCatalog,
  type DataDataset,
  type DataPage,
  type DataProvenance,
  type DataRecord,
} from '@/lib/data-api';

const PAGE_SIZE = 25;
const domainIcons = {
  academic: GraduationCap,
  operational: Users,
  cases: BriefcaseBusiness,
  governance: ShieldCheck,
} as const;

const provenanceLabels: Record<DataProvenance, string> = {
  real: 'Real NTU/CCDS',
  simulated: 'Simulated',
  derived: 'Derived',
  restricted: 'Restricted',
};

function ProvenancePill({ kind }: { kind: DataProvenance }) {
  return <span className={`data-provenance data-provenance-${kind}`}>{provenanceLabels[kind]}</span>;
}

export function DataExplorer() {
  const [catalog, setCatalog] = useState<DataCatalog | null>(null);
  const [datasetId, setDatasetId] = useState('courses');
  const [dataPage, setDataPage] = useState<DataPage | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [programme, setProgramme] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState('');
  const [direction, setDirection] = useState<'asc' | 'desc'>('asc');
  const [loadedRequest, setLoadedRequest] = useState('');
  const [error, setError] = useState<string | null>(null);
  const requestKey = `${datasetId}|${page}|${debouncedSearch}|${programme}|${status}|${sort}|${direction}`;
  const loading = loadedRequest !== requestKey;

  useEffect(() => {
    const controller = new AbortController();
    fetchDataCatalog(controller.signal)
      .then((result) => {
        setCatalog(result);
        setError(null);
      })
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') setError(reason.message);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search), 220);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    const controller = new AbortController();
    fetchDataPage(
      datasetId,
      { page, pageSize: PAGE_SIZE, search: debouncedSearch, programme, status, sort, direction },
      controller.signal,
    )
      .then((result) => {
        setDataPage(result);
        setSelectedId((current) =>
          result.records.some((record) => record.record_id === current)
            ? current
            : (result.records[0]?.record_id ?? null),
        );
        setError(null);
        setLoadedRequest(requestKey);
      })
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') {
          setError(reason.message);
          setLoadedRequest(requestKey);
        }
      });
    return () => controller.abort();
  }, [datasetId, page, debouncedSearch, programme, status, sort, direction, requestKey]);

  const selectedRecord = useMemo(
    () => dataPage?.records.find((record) => record.record_id === selectedId) ?? null,
    [dataPage, selectedId],
  );
  const totalPages = Math.max(1, Math.ceil((dataPage?.total ?? 0) / PAGE_SIZE));

  function chooseDataset(dataset: DataDataset) {
    if (!dataset.accessible) return;
    setDatasetId(dataset.dataset_id);
    setSearch('');
    setDebouncedSearch('');
    setProgramme('');
    setStatus('');
    setPage(1);
    setSort(dataset.default_sort ?? '');
    setDirection('asc');
  }

  function changeSort(key: string) {
    if (sort === key) setDirection((current) => current === 'asc' ? 'desc' : 'asc');
    else {
      setSort(key);
      setDirection('asc');
    }
    setPage(1);
  }

  function followRelationship(targetDataset: string, targetId?: string) {
    const dataset = catalog?.datasets.find((item) => item.dataset_id === targetDataset);
    if (!dataset?.accessible) return;
    setDatasetId(targetDataset);
    setSearch(targetId ?? '');
    setDebouncedSearch(targetId ?? '');
    setProgramme('');
    setStatus('');
    setPage(1);
    setSort(dataset.default_sort ?? '');
  }

  return (
    <AppShell activeSection="data" workspace systemStatus={error ? 'offline' : catalog ? 'operational' : 'checking'}>
      <section className="data-explorer" aria-label="Grounded data explorer">
        <header className="data-overview-bar">
          <div className="data-overview-title">
            <span className="data-icon-box"><Database size={21} /></span>
            <div>
              <strong>Grounded data explorer</strong>
              <span>Read-only processed views with record-level provenance</span>
            </div>
          </div>
          {catalog ? (
            <div className="data-stat-strip" aria-label="Catalogue statistics">
              <span><b>{catalog.stats.datasets}</b> data sets</span>
              <span><b>{catalog.stats.accessible_records.toLocaleString()}</b> inspectable records</span>
              <span><b>{catalog.stats.real_records.toLocaleString()}</b> real</span>
              <span><b>{catalog.stats.simulated_records.toLocaleString()}</b> simulated</span>
              <span className="data-stat-restricted"><LockKeyhole size={13} /> {catalog.stats.restricted_records} protected</span>
            </div>
          ) : null}
        </header>

        {error ? (
          <div className="data-error-banner" role="alert">
            <AlertTriangle size={18} />
            <span><strong>Data API unavailable.</strong> {error}</span>
            <button type="button" onClick={() => window.location.reload()}><RefreshCw size={15} /> Retry</button>
          </div>
        ) : null}

        <div className="data-explorer-grid">
          <aside className="data-catalog-panel" aria-label="Data sets">
            <div className="data-panel-heading">
              <BookOpenCheck size={18} />
              <strong>Catalogue</strong>
            </div>
            <div className="data-domain-list">
              {catalog?.domains.map((domain) => {
                const Icon = domainIcons[domain.domain];
                const datasets = catalog.datasets.filter((item) => item.domain === domain.domain);
                return (
                  <section className="data-domain" key={domain.domain}>
                    <div className="data-domain-title"><Icon size={16} /><span>{domain.label}</span></div>
                    <div className="data-dataset-list">
                      {datasets.map((dataset) => (
                        <button
                          type="button"
                          key={dataset.dataset_id}
                          className={`data-dataset-button${dataset.dataset_id === datasetId ? ' is-active' : ''}${!dataset.accessible ? ' is-restricted' : ''}`}
                          onClick={() => chooseDataset(dataset)}
                          aria-pressed={dataset.dataset_id === datasetId}
                          disabled={!dataset.accessible}
                          title={!dataset.accessible ? 'Evaluator-only data is protected' : dataset.description}
                        >
                          <span>{!dataset.accessible ? <LockKeyhole size={12} /> : null}{dataset.label}</span>
                          <small>{dataset.record_count.toLocaleString()}</small>
                        </button>
                      ))}
                    </div>
                  </section>
                );
              }) ?? <CatalogueSkeleton />}
            </div>
            <div className="data-boundary-note">
              <ShieldCheck size={16} />
              <p><strong>Safe inspection boundary</strong>Ground truth, injected events and transaction scripts are not exposed.</p>
            </div>
          </aside>

          <main className="data-table-panel">
            <div className="data-table-titlebar">
              <div>
                <div className="data-title-line">
                  <h1>{dataPage?.dataset.label ?? 'Loading catalogue'}</h1>
                  {dataPage ? <ProvenancePill kind={dataPage.dataset.provenance} /> : null}
                </div>
                <p>{dataPage?.dataset.description ?? 'Connecting to the read-only data service…'}</p>
              </div>
              <span className="data-result-count">{dataPage?.total.toLocaleString() ?? '—'} records</span>
            </div>

            <div className="data-toolbar">
              <label className="data-search-field">
                <Search size={17} />
                <input
                  value={search}
                  onChange={(event) => { setSearch(event.target.value); setPage(1); }}
                  placeholder="Search IDs, titles, fields or lineage…"
                  aria-label="Search records"
                />
              </label>
              <label>
                <span className="sr-only">Programme</span>
                <select value={programme} onChange={(event) => { setProgramme(event.target.value); setPage(1); }}>
                  <option value="">All programmes</option>
                  {dataPage?.filters.programmes.map((item) => <option key={item}>{item}</option>)}
                </select>
              </label>
              <label>
                <span className="sr-only">Status</span>
                <select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
                  <option value="">All statuses</option>
                  {dataPage?.filters.statuses.map((item) => <option key={item}>{item}</option>)}
                </select>
              </label>
            </div>

            <div className={`data-table-wrap${loading ? ' is-loading' : ''}`}>
              <table aria-label={`${dataPage?.dataset.label ?? 'Data'} records`} className="data-record-table">
                <thead>
                  <tr>
                    {dataPage?.dataset.columns.map((column) => (
                      <th aria-sort={sort === column.key ? (direction === 'asc' ? 'ascending' : 'descending') : undefined} key={column.key} scope="col">
                        <button type="button" onClick={() => changeSort(column.key)}>
                          {column.label}
                          {sort === column.key
                            ? direction === 'asc' ? <ArrowUp size={13} /> : <ArrowDown size={13} />
                            : null}
                        </button>
                      </th>
                    ))}
                    <th className="data-row-open" scope="col"><span className="sr-only">Open</span></th>
                  </tr>
                </thead>
                <tbody>
                  {dataPage?.records.map((record) => (
                    <tr
                      key={record.record_id}
                      aria-selected={record.record_id === selectedId}
                      className={record.record_id === selectedId ? 'is-selected' : ''}
                      onClick={() => setSelectedId(record.record_id)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          setSelectedId(record.record_id);
                        }
                      }}
                      tabIndex={0}
                    >
                      {dataPage.dataset.columns.map((column, index) => (
                        <td key={column.key}>
                          {column.kind === 'status' ? (
                            <span className={`data-status data-status-${statusTone(record.cells[column.key])}`}>{record.cells[column.key] || '—'}</span>
                          ) : index === 0 ? (
                            <strong>{record.cells[column.key] || '—'}</strong>
                          ) : (
                            <span title={record.cells[column.key]}>{record.cells[column.key] || '—'}</span>
                          )}
                        </td>
                      ))}
                      <td className="data-row-open"><ChevronRight size={16} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!loading && dataPage?.records.length === 0 ? (
                <div className="data-empty-state"><Search size={28} /><strong>No matching records</strong><span>Try clearing one of the filters.</span></div>
              ) : null}
              {loading ? <div aria-live="polite" className="data-loading-overlay" role="status"><RefreshCw size={19} className="is-spinning" /> Updating table…</div> : null}
            </div>

            <footer className="data-pagination">
              <span>{dataPage?.total ? `${((page - 1) * PAGE_SIZE + 1).toLocaleString()}–${Math.min(page * PAGE_SIZE, dataPage.total).toLocaleString()} of ${dataPage.total.toLocaleString()}` : '0 records'}</span>
              <div>
                <button type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}><ChevronLeft size={16} /> Previous</button>
                <span>Page {page} of {totalPages}</span>
                <button type="button" disabled={page >= totalPages} onClick={() => setPage((value) => value + 1)}>Next <ChevronRight size={16} /></button>
              </div>
            </footer>
          </main>

          <RecordInspector record={selectedRecord} onFollow={followRelationship} />
        </div>
      </section>
    </AppShell>
  );
}

function RecordInspector({
  record,
  onFollow,
}: {
  record: DataRecord | null;
  onFollow: (datasetId: string, recordId?: string) => void;
}) {
  return (
    <aside className="data-inspector-panel" aria-label="Record inspector">
      <div className="data-panel-heading"><FileCheck2 size={18} /><strong>Record inspector</strong></div>
      {record ? (
        <div className="data-inspector-scroll">
          <div className="data-record-identity">
            <ProvenancePill kind={record.provenance} />
            <h2>{record.title}</h2>
            <p>{record.subtitle}</p>
            <code>{record.record_id}</code>
          </div>

          {record.sections.map((section) => (
            <section className="data-inspector-section" key={section.title}>
              <h3>{section.title}</h3>
              <dl>
                {section.fields.map((field) => (
                  <div key={field.label}>
                    <dt>{field.label}</dt>
                    <dd>{/^https:\/\//.test(field.value) ? <a href={field.value} target="_blank" rel="noreferrer">Open authoritative source</a> : field.value}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}

          {record.relationships.length ? (
            <section className="data-inspector-section">
              <h3><Link2 size={15} /> Related records</h3>
              <div className="data-relationship-list">
                {record.relationships.map((relationship) => (
                  <button type="button" key={`${relationship.dataset_id}-${relationship.label}`} onClick={() => onFollow(relationship.dataset_id, relationship.record_ids[0])}>
                    <span><strong>{relationship.label}</strong><small>{relationship.record_ids.slice(0, 2).join(', ')}</small></span>
                    <b>{relationship.total_count}</b><ChevronRight size={15} />
                  </button>
                ))}
              </div>
            </section>
          ) : null}

          {record.source_ids.length || record.lineage_ids.length ? (
            <section className="data-inspector-section">
              <h3><ShieldCheck size={15} /> Provenance & lineage</h3>
              {record.source_ids.length ? <TokenList label="Authoritative sources" items={record.source_ids} /> : null}
              {record.lineage_ids.length ? <TokenList label="Simulation rule lineage" items={record.lineage_ids} /> : null}
            </section>
          ) : null}

          {record.quality_notes.length ? (
            <section className="data-inspector-section data-quality-section">
              <h3><AlertTriangle size={15} /> Known gaps & limitations</h3>
              <ul>{record.quality_notes.map((note, index) => <li key={`${index}-${note}`}>{note}</li>)}</ul>
            </section>
          ) : null}

          <div className="data-raw-boundary"><LockKeyhole size={15} /><span><strong>Processed view only</strong>Raw payloads and evaluator-only fields are disabled on this surface.</span></div>
        </div>
      ) : (
        <div className="data-inspector-empty"><Database size={28} /><strong>Select a record</strong><span>Its processed summary, relationships and provenance will appear here.</span></div>
      )}
    </aside>
  );
}

function TokenList({ label, items }: { label: string; items: string[] }) {
  return (
    <div className="data-token-group">
      <span>{label}</span>
      <div>{items.map((item) => <code key={item}>{item}</code>)}</div>
    </div>
  );
}

function CatalogueSkeleton() {
  return <div className="data-catalogue-skeleton"><i /><i /><i /><i /><i /><i /></div>;
}

function statusTone(value = '') {
  const normalized = value.toLowerCase();
  if (/complete|retrieved|approved|available|active|ready|resolved|good|explicit|offered/.test(normalized)) return 'good';
  if (/partial|pending|unknown|unavailable|waiting|restricted/.test(normalized)) return 'warn';
  if (/error|failed|rejected|blocked|inactive/.test(normalized)) return 'bad';
  return 'neutral';
}
