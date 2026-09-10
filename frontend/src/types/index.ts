

export interface UserPayload {
  readonly user_id: string;
  readonly email: string;
}


export type AuthState =
  | { readonly status: 'idle' }
  | { readonly status: 'loading' }
  | { readonly status: 'success' }
  | { readonly status: 'error'; readonly message: string };


export type ApiResponse<T> =
  | { readonly success: true; readonly data: T; readonly error: null }
  | { readonly success: false; readonly data: null; readonly error: string };

export interface Citation {
  readonly filename: string;
  readonly page_number: number;
  readonly content: string;
}

export type EnrichmentStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface EnrichmentStatusInfo {
  readonly status: EnrichmentStatus;
  readonly total_paragraphs: number;
  readonly processed_paragraphs: number;
  readonly question_chunks_created: number;
  readonly failed_paragraphs: number;
}

export interface DocumentItem {
  readonly id: string;
  readonly filename: string;
  readonly file_size: number;
  readonly total_pages?: number;
  readonly is_active?: boolean;
  readonly status?: 'processing' | 'ready' | 'failed';
  readonly created_at: string;
  readonly enrichment?: EnrichmentStatusInfo | null;
}

export interface DocumentPreviewResponse {
  readonly document_id: string;
  readonly signed_url: string;
}

export interface ChatSession {
  readonly id: string;
  readonly title: string;
  readonly created_at: string;
}

export interface ChatMessage {
  readonly id: string;
  readonly sender: 'user' | 'assistant';
  readonly content: string;
  readonly citations?: readonly Citation[];
  readonly created_at: string;
}

export type ProviderType = 'gemini' | 'openai' | 'openrouter' | 'openai_compatible';

export const PROVIDER_OPTIONS: { type: ProviderType; label: string }[] = [
  { type: 'gemini', label: 'Google Gemini' },
  { type: 'openai', label: 'OpenAI' },
  { type: 'openrouter', label: 'OpenRouter' },
  { type: 'openai_compatible', label: 'OpenAI-Compatible' },
];

export interface ProviderConfig {
  readonly id: string;
  readonly provider: ProviderType;
  readonly display_name: string | null;
  readonly base_url: string | null;
  readonly model_name: string | null;
  readonly is_default: boolean;
}

export interface ProviderConfigCreatePayload {
  readonly provider: ProviderType;
  readonly api_key: string;
  readonly display_name?: string;
  readonly base_url?: string;
  readonly model_name?: string;
  readonly is_default?: boolean;
}

export interface ProviderConfigUpdatePayload {
  readonly display_name?: string;
  readonly api_key?: string;
  readonly base_url?: string;
  readonly model_name?: string;
  readonly is_default?: boolean;
}

export interface EmbeddingConfig {
  readonly provider: string;
  readonly base_url: string | null;
  readonly model_name: string;
  readonly embedding_dimensions?: number | null;
  readonly locked: boolean;
}

export interface EmbeddingConfigSavePayload {
  readonly provider: string;
  readonly api_key?: string;
  readonly base_url?: string;
  readonly model_name: string;
  readonly embedding_dimensions?: number | null;
}

export type EnrichmentPreset = 'off' | 'standard' | 'high' | 'full';

export interface EnrichmentConfig {
  readonly preset: EnrichmentPreset;
  readonly max_enriched_paragraphs: number;
}

export interface EnrichmentConfigSavePayload {
  readonly preset: EnrichmentPreset;
}


