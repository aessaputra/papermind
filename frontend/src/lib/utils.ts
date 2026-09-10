import type { ProviderConfig } from '@/types';
import { PROVIDER_OPTIONS } from '@/types';

export const formatModelName = (name: string): string => {
  return name
    .replace(/^models\//, '')
    .replace(/\//g, ' - ')
    .replace(/[:_]/g, ' ')
    .replace(/(?<!\s)-(?!\s)/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
};

export const formatProviderLabel = (cfg?: ProviderConfig, fallbackProvider?: string): string => {
  if (!cfg) return fallbackProvider?.toUpperCase() || 'Pilih Provider';
  if (cfg.display_name) return cfg.display_name;
  
  const option = PROVIDER_OPTIONS.find((opt) => opt.type === cfg.provider);
  if (option) return option.label;

  const name = cfg.provider;
  return name.charAt(0).toUpperCase() + name.slice(1);
};

export const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

export function isNetworkError(message: string): boolean {
  return message.includes('Failed to fetch') || message.includes('NetworkError');
}
