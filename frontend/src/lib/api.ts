import type { ApiResponse, ChatMessage, ChatSession, Citation, DocumentItem, DocumentPreviewResponse, ProviderConfig, ProviderConfigCreatePayload, ProviderConfigUpdatePayload, EmbeddingConfig, EmbeddingConfigSavePayload, EnrichmentConfig, EnrichmentConfigSavePayload } from '@/types';


import { createClient } from '@/lib/supabaseClient';
import { isNetworkError } from '@/lib/utils';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';


async function getAuthHeaders(fallbackToken?: string): Promise<Record<string, string>> {
  if (fallbackToken) {
    return { Authorization: `Bearer ${fallbackToken}` };
  }
  try {
    const { data } = await createClient().auth.getSession();
    const token = data.session?.access_token;
    if (token) return { Authorization: `Bearer ${token}` };
  } catch {}
  throw new Error('Sesi login telah berakhir. Silakan login kembali.');
}

async function extractErrorDetail(response: Response, fallback: string): Promise<string> {
  try {
    const text = await response.text();
    if (!text.trim()) return `Error HTTP ${response.status}: ${fallback}`;

    try {
      const json = JSON.parse(text);
      const detail = json.detail || json.message || json.error;
      if (detail) return typeof detail === 'string' ? detail : JSON.stringify(detail);
    } catch { }
    return `Error HTTP ${response.status}: ${text.substring(0, 200)}`;
  } catch {
    return `Error HTTP ${response.status}: ${fallback}`;
  }
}

async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {},
  token?: string,
  fallbackError: string = 'Terjadi kesalahan jaringan.',
  requireAuth: boolean = true
): Promise<ApiResponse<T>> {
  try {
    const headers = requireAuth ? await getAuthHeaders(token) : undefined;
    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers: {
        ...options.headers,
        ...headers,
      },
    });

    // GET 404 (e.g. embedding config unset) and DELETE 404 (already deleted
    // elsewhere) both count as success: deletes are idempotent.
    if (response.status === 404 && (options.method === 'GET' || options.method === 'DELETE')) {
      return { success: true, data: null as any, error: null };
    }

    if (!response.ok) {
      return { success: false, data: null as any, error: await extractErrorDetail(response, fallbackError) };
    }

    const text = await response.text();
    const data = text ? JSON.parse(text) : true;
    
    return { success: true, data, error: null };
  } catch (err: any) {
    const message = err.message || '';
    if (isNetworkError(message)) {
      return { success: false, data: null as any, error: `Gagal terhubung ke server backend di ${API_BASE}` };
    }
    return { success: false, data: null as any, error: message || 'Terjadi kesalahan jaringan.' };
  }
}



interface SSEStreamCallbacks {
  onSession?: (sessionId: string) => void;
  onCitations: (citations: Citation[]) => void;
  onToken: (token: string) => void;
  onComplete: () => void;
  onError: (message: string) => void;
}

export async function fetchSSEStream(
  query: string,
  token: string,
  provider: string,
  documentIds: string[] | undefined,
  callbacks: SSEStreamCallbacks,
  sessionId?: string
): Promise<void> {
  try {
    const headers = await getAuthHeaders(token);

    const response = await fetch(`${API_BASE}/api/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...headers },
      body: JSON.stringify({
        query,
        provider,
        document_ids: documentIds?.length ? documentIds : undefined,
        session_id: sessionId || undefined,
      }),
    });

    if (!response.ok) {
      callbacks.onError(await extractErrorDetail(response, 'Gagal mengambil jawaban AI.'));
      return;
    }

    await consumeSSEStream(response, callbacks);
    callbacks.onComplete();
  } catch (err: any) {
    callbacks.onError(err.message || 'Terjadi kesalahan jaringan.');
  }
}

async function consumeSSEStream(response: Response, callbacks: SSEStreamCallbacks) {
  const reader = response.body?.getReader();
  if (!reader) {
    callbacks.onError('Respons stream tidak didukung oleh browser.');
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop() || '';

    for (const block of events) {
      parseSSEEvent(block, callbacks);
    }
  }
}

function parseSSEEvent(block: string, callbacks: SSEStreamCallbacks) {
  try {
    if (block.startsWith('event: session')) {
      const json = block.replace('event: session\ndata: ', '').trim();
      if (json && callbacks.onSession) {
        const data = JSON.parse(json);
        if (data.session_id) callbacks.onSession(data.session_id);
      }
    } else if (block.startsWith('event: citations')) {
      const json = block.replace('event: citations\ndata: ', '').trim();
      if (json) callbacks.onCitations(JSON.parse(json));
    } else if (block.startsWith('event: token')) {
      const json = block.replace('event: token\ndata: ', '').trim();
      if (json) {
        const data = JSON.parse(json);
        if (data.token) callbacks.onToken(data.token);
      }
    }
  } catch (err) {
    console.error('SSE parse error:', err);
  }
}



export function listChatSessions(token: string): Promise<ApiResponse<ChatSession[]>> {
  return apiFetch('/api/chat/sessions', undefined, token, 'Gagal mengambil riwayat sesi.');
}

export function getSessionMessages(sessionId: string, token: string): Promise<ApiResponse<ChatMessage[]>> {
  return apiFetch(`/api/chat/sessions/${sessionId}/messages`, undefined, token, 'Gagal mengambil pesan percakapan.');
}

export function deleteChatSession(sessionId: string, token: string): Promise<ApiResponse<boolean>> {
  return apiFetch(`/api/chat/sessions/${sessionId}`, { method: 'DELETE' }, token, 'Gagal menghapus sesi percakapan.');
}



export function uploadDocument(file: File, token: string): Promise<ApiResponse<any>> {
  const formData = new FormData();
  formData.append('file', file);
  return apiFetch('/api/documents/upload', { method: 'POST', body: formData }, token, 'Gagal mengunggah PDF.');
}

export function listDocuments(token: string): Promise<ApiResponse<DocumentItem[]>> {
  return apiFetch('/api/documents', undefined, token, 'Gagal mengambil daftar dokumen.');
}

export function deleteDocument(documentId: string, token: string): Promise<ApiResponse<boolean>> {
  return apiFetch(`/api/documents/${documentId}`, { method: 'DELETE' }, token, 'Gagal menghapus dokumen.');
}

export function toggleDocumentActive(documentId: string, isActive: boolean, token: string): Promise<ApiResponse<DocumentItem>> {
  return apiFetch(
    `/api/documents/${documentId}/toggle`,
    { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ is_active: isActive }) },
    token,
    'Gagal mengubah status dokumen.'
  );
}

export function getDocumentPreviewUrl(documentId: string, token: string): Promise<ApiResponse<DocumentPreviewResponse>> {
  return apiFetch(`/api/documents/${documentId}/preview`, { method: 'GET' }, token, 'Gagal mengambil URL preview dokumen.');
}



export function listProviderConfigs(token: string): Promise<ApiResponse<ProviderConfig[]>> {
  return apiFetch('/api/settings/providers', undefined, token, 'Gagal mengambil daftar provider.');
}

export function createProviderConfig(
  payload: ProviderConfigCreatePayload,
  token: string
): Promise<ApiResponse<ProviderConfig>> {
  return apiFetch(
    '/api/settings/providers',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) },
    token,
    'Gagal menambahkan provider.'
  );
}

export function updateProviderConfig(
  id: string,
  payload: ProviderConfigUpdatePayload,
  token: string
): Promise<ApiResponse<ProviderConfig>> {
  return apiFetch(
    `/api/settings/providers/${id}`,
    { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) },
    token,
    'Gagal memperbarui provider.'
  );
}

export function deleteProviderConfig(id: string, token: string): Promise<ApiResponse<boolean>> {
  return apiFetch(`/api/settings/providers/${id}`, { method: 'DELETE' }, token, 'Gagal menghapus provider.');
}


export function getEmbeddingConfig(token: string): Promise<ApiResponse<EmbeddingConfig | null>> {
  return apiFetch('/api/settings/embedding', { method: 'GET' }, token, 'Gagal mengambil konfigurasi embedding.');
}

export function saveEmbeddingConfig(
  payload: EmbeddingConfigSavePayload,
  token: string
): Promise<ApiResponse<EmbeddingConfig>> {
  return apiFetch(
    '/api/settings/embedding',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) },
    token,
    'Gagal menyimpan konfigurasi embedding.'
  );
}

export function getEnrichmentConfig(token: string): Promise<ApiResponse<EnrichmentConfig>> {
  return apiFetch('/api/settings/enrichment', { method: 'GET' }, token, 'Gagal mengambil konfigurasi enrichment.');
}

export function saveEnrichmentConfig(
  payload: EnrichmentConfigSavePayload,
  token: string
): Promise<ApiResponse<EnrichmentConfig>> {
  return apiFetch(
    '/api/settings/enrichment',
    { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) },
    token,
    'Gagal menyimpan konfigurasi enrichment.'
  );
}

interface VerifyModelsResponseData {
  success: boolean;
  models: string[];
  default_model: string;
  probed_dimension?: number | null;
  error?: string | null;
}

export function verifyAndFetchModels(
  provider: string,
  apiKey?: string,
  baseUrl?: string,
  configId?: string,
  token?: string,
  modelType: 'chat' | 'embedding' = 'chat'
): Promise<ApiResponse<VerifyModelsResponseData>> {
  return apiFetch(
    '/api/settings/providers/verify-models',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider,
        model_type: modelType,
        api_key: apiKey || undefined,
        base_url: baseUrl || undefined,
        config_id: configId || undefined,
      }),
    },
    token,
    'Gagal memverifikasi model provider.'
  );
}



