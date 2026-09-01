export type DataProvenance = 'real' | 'simulated' | 'derived' | 'restricted';
export type DataDomain = 'academic' | 'operational' | 'cases' | 'governance';

export type DataColumn = {
  key: string;
  label: string;
  kind: 'text' | 'number' | 'status' | 'date' | 'list';
};

export type DataDataset = {
  dataset_id: string;
  domain: DataDomain;
  label: string;
  description: string;
  provenance: DataProvenance;
  record_count: number;
  accessible: boolean;
  columns: DataColumn[];
  default_sort: string | null;
};

export type DataCatalog = {
  api_version: '1.0';
  domains: Array<{
    domain: DataDomain;
    label: string;
    description: string;
    dataset_ids: string[];
  }>;
  datasets: DataDataset[];
  stats: {
    datasets: number;
    accessible_records: number;
    real_records: number;
    simulated_records: number;
    restricted_records: number;
  };
};

export type DataRecord = {
  record_id: string;
  title: string;
  subtitle: string;
  provenance: DataProvenance;
  status: string | null;
  cells: Record<string, string>;
  sections: Array<{ title: string; fields: Array<{ label: string; value: string }> }>;
  relationships: Array<{
    label: string;
    dataset_id: string;
    record_ids: string[];
    total_count: number;
  }>;
  source_ids: string[];
  lineage_ids: string[];
  quality_notes: string[];
};

export type DataPage = {
  api_version: '1.0';
  dataset: DataDataset;
  page: number;
  page_size: number;
  total: number;
  records: DataRecord[];
  filters: { programmes: string[]; statuses: string[] };
};

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '');

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Data request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

export function fetchDataCatalog(signal?: AbortSignal) {
  return get<DataCatalog>('/api/v1/data/catalog', signal);
}

export function fetchDataPage(
  datasetId: string,
  query: {
    page: number;
    pageSize: number;
    search: string;
    programme: string;
    status: string;
    sort: string;
    direction: 'asc' | 'desc';
  },
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({
    page: String(query.page),
    page_size: String(query.pageSize),
    search: query.search,
    programme: query.programme,
    status: query.status,
    sort: query.sort,
    direction: query.direction,
  });
  return get<DataPage>(`/api/v1/data/${encodeURIComponent(datasetId)}?${params}`, signal);
}
