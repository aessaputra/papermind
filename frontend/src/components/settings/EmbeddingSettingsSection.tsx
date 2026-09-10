'use client';

import React, { useState, useDeferredValue, useEffect } from 'react';
import Link from 'next/link';
import { LayersIcon, LockClosedIcon, ChevronDownIcon, ChevronUpIcon, CheckIcon } from '@radix-ui/react-icons';
import * as Select from '@radix-ui/react-select';
import useSWR from 'swr';
import { saveEmbeddingConfig, verifyAndFetchModels } from '@/lib/api';
import type { EmbeddingConfig, ProviderConfig } from '@/types';
import { PROVIDER_OPTIONS } from '@/types';
import { formatModelName } from '@/lib/utils';



interface EmbeddingSettingsSectionProps {
  readonly configs: ProviderConfig[];
  readonly embeddingConfig: EmbeddingConfig | null;
  readonly token: string;
  readonly onSetEmbeddingConfig: (config: EmbeddingConfig) => void;
  readonly onSetSuccessMsg: (msg: string | null) => void;
  readonly onSetErrorMsg: (msg: string | null) => void;
}

function EmbeddingSettingsSection({
  configs,
  embeddingConfig,
  token,
  onSetEmbeddingConfig,
  onSetSuccessMsg,
  onSetErrorMsg,
}: EmbeddingSettingsSectionProps) {
  const defaultProvider = configs.find(c => c.is_default)?.provider || configs[0]?.provider || PROVIDER_OPTIONS[0].type;
  const [embProvider, setEmbProvider] = useState<string>(embeddingConfig?.provider || defaultProvider);
  const [embModelName, setEmbModelName] = useState<string>(embeddingConfig?.model_name || '');
  const [embDimensions, setEmbDimensions] = useState<number | ''>(embeddingConfig?.embedding_dimensions || '');
  const [embBaseUrl, setEmbBaseUrl] = useState<string>(embeddingConfig?.base_url || '');
  const [embError, setEmbError] = useState<string | null>(null);
  const [isSavingEmbedding, setIsSavingEmbedding] = useState(false);
  const [isCustomModelInput, setIsCustomModelInput] = useState(false);
  const [prevRes, setPrevRes] = useState<any>(null);

  const deferredBaseUrl = useDeferredValue(embBaseUrl.trim());
  const targetConfigId = configs.find((c) => c.provider === embProvider)?.id;

  const fetcherKey = embeddingConfig?.locked || !targetConfigId
    ? null
    : ['verifyAndFetchModels', embProvider, deferredBaseUrl, targetConfigId, token, 'embedding'];

  const fetcher = async ([, prov, url, cid, tok, type]: any) => {
    return verifyAndFetchModels(prov, undefined, url || undefined, cid || undefined, tok, type);
  };

  const { data: res, isLoading: isLoadingEmbModels } = useSWR(fetcherKey, fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 60000,
  });

  const fetchedEmbModels = res?.data?.models || [];
  const fetchError = res?.error || res?.data?.error || null;
  const probedDims = res?.data?.probed_dimension || null;

  useEffect(() => {
    if (res !== prevRes) {
      setPrevRes(res);
      if (res?.success && res.data?.models && res.data.models.length > 0 && !embModelName) {
        setEmbModelName(res.data.default_model || '');
      }
    }
  }, [res, prevRes, embModelName]);

  const handleSaveEmbedding = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (embeddingConfig?.locked) return;

    setEmbError(null);
    onSetErrorMsg(null);
    onSetSuccessMsg(null);

    if (!embModelName.trim()) {
      setEmbError('Nama model embedding wajib diisi.');
      return;
    }
    if (embDimensions !== '' && embDimensions < 64) {
      setEmbError('Dimensi vektor minimal 64.');
      return;
    }

    setIsSavingEmbedding(true);

    try {
      const payload = {
        provider: embProvider,
        model_name: embModelName.trim(),
        embedding_dimensions: embDimensions === '' ? null : embDimensions,
        base_url: embBaseUrl.trim() || undefined,
      };

      const res = await saveEmbeddingConfig(payload, token);
      if (!res.success) {
        setEmbError(res.error || 'Gagal menyimpan konfigurasi embedding.');
        return;
      }

      onSetEmbeddingConfig(res.data);
      onSetSuccessMsg('Model embedding berhasil disimpan.');
    } catch (err: any) {
      setEmbError(err.message || 'Terjadi kesalahan sistem.');
    } finally {
      setIsSavingEmbedding(false);
    }
  };

  const options = [...fetchedEmbModels];
  if (embModelName && !options.includes(embModelName) && embModelName !== '__custom__') {
    options.unshift(embModelName);
  }

  return (
    <section
      aria-label="Konfigurasi Model Embedding Dokumen"
      className="p-6 rounded-xl bg-surface-card border border-subtle h-full flex flex-col space-y-6"
    >
      <div className="flex items-center justify-between border-b border-subtle pb-4">
        <h2 className="text-sm font-serif tracking-tight text-primary flex items-center gap-2">
          <LayersIcon className="w-4 h-4 text-muted" aria-hidden="true" />
          <span>Embedding</span>
        </h2>
        {embeddingConfig?.locked ? (
          <span className="text-xs font-serif text-muted flex items-center gap-1.5" aria-hidden="true">
            <LockClosedIcon className="w-3.5 h-3.5" /> Terkunci
          </span>
        ) : null}
      </div>


      {embeddingConfig?.locked ? (
        <div className="p-5 mt-2 rounded-xl bg-surface-card-hover/50 border border-subtle text-sm flex flex-col items-center justify-center space-y-4 text-center">
          <div className="w-10 h-10 rounded-full bg-canvas border border-subtle flex items-center justify-center text-muted shadow-xs">
            <LockClosedIcon className="w-4 h-4" />
          </div>
          <div>
            <p className="text-primary font-medium tracking-tight mb-0.5">Model Terkunci</p>
            <p className="text-muted text-xs">Sedang digunakan oleh dokumen aktif.</p>
          </div>
          <Link 
            href="/" 
            className="minimal-button-secondary px-4 py-2 rounded-md text-xs font-medium inline-flex items-center gap-1.5 focus-visible:ring-2 focus-visible:ring-zinc-400"
          >
            &larr; Chat
          </Link>
        </div>
      ) : null}

      {embError ? (
        <div
          role="alert"
          className="p-3 rounded-md bg-(--pastel-red-bg) border border-(--pastel-red-text)/20 text-(--pastel-red-text) text-xs leading-normal"
        >
          {embError}
        </div>
      ) : null}

      <form onSubmit={handleSaveEmbedding} className="flex-1 space-y-5 flex flex-col">

        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label htmlFor="embProvider" className="block text-xs font-mono uppercase tracking-wider text-muted">
              PROVIDER
            </label>
            {!targetConfigId && !embeddingConfig?.locked ? (
              <span className="text-xs font-mono text-(--pastel-red-text)">
                Belum dikonfigurasi di Chat
              </span>
            ) : null}
          </div>
          <select
            id="embProvider"
            disabled={!!embeddingConfig?.locked}
            value={embProvider}
            onChange={(e) => {
              const newProv = e.target.value;
              setEmbProvider(newProv);
              setEmbModelName('');
              setEmbDimensions('');
              setIsCustomModelInput(false);
            }}
            className="minimal-input w-full px-3 py-2 rounded-md text-xs cursor-pointer disabled:opacity-50"
          >
            {PROVIDER_OPTIONS.map((opt) => (
              <option key={opt.type} value={opt.type} className="bg-surface-card text-primary">
                {opt.label}
              </option>
            ))}
          </select>
        </div>


        <div className="p-3.5 rounded-md bg-surface-card-hover border border-subtle space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-2">
              <div className="flex items-center justify-between mb-1.5">
                <label htmlFor="embModelSelect" className="block text-xs font-mono uppercase tracking-wider text-muted">
                  MODEL
                </label>
                {isLoadingEmbModels ? (
                  <span className="text-xs font-mono text-muted animate-pulse truncate text-right ml-2" title="Memuat model">
                    Loading…
                  </span>
                ) : !targetConfigId ? (
                  <span className="text-xs font-mono text-zinc-500/50 truncate text-right ml-2" title="Menunggu konfigurasi kunci API di bagian Provider Chat">
                    Menunggu kunci…
                  </span>
                ) : fetchError ? (
                  <span className="text-xs font-mono text-(--pastel-red-text) truncate text-right ml-2" title={fetchError}>
                    Error
                  </span>
                ) : null}
              </div>

              {!isCustomModelInput ? (
                <Select.Root
                  value={embModelName || undefined}
                  onValueChange={(val) => {
                    if (val === '__custom__') {
                      setIsCustomModelInput(true);
                      setEmbModelName('');
                    } else {
                      setEmbModelName(val);
                      setEmbDimensions('');
                    }
                  }}
                  disabled={!!embeddingConfig?.locked || !targetConfigId}
                >
                  <Select.Trigger
                    id="embModelSelect"
                    className="minimal-input w-full px-3 py-2 rounded-md text-xs font-mono cursor-pointer disabled:opacity-50 flex items-center justify-between gap-2 text-left [&>span]:line-clamp-1 bg-surface-card outline-none focus-visible:ring-2 border-subtle text-primary focus-visible:ring-zinc-400"
                  >
                    <Select.Value placeholder="Pilih model…" />
                    <Select.Icon>
                      <ChevronDownIcon className="w-3.5 h-3.5 opacity-50" />
                    </Select.Icon>
                  </Select.Trigger>
                  
                  <Select.Portal>
                    <Select.Content position="popper" sideOffset={4} className="overflow-hidden bg-surface-card border border-subtle rounded-md shadow-lg shadow-black/20 z-100 w-(--radix-select-trigger-width) max-h-[60vh]">
                      <Select.ScrollUpButton className="flex items-center justify-center h-6.25 bg-surface-card text-primary cursor-default">
                        <ChevronUpIcon className="w-3.5 h-3.5" />
                      </Select.ScrollUpButton>
                      <Select.Viewport className="p-1">
                        {options.map((m) => (
                          <Select.Item key={m} value={m} className="relative flex min-w-0 items-center pl-6 pr-3 py-2 text-xs font-mono text-primary rounded-[3px] select-none data-highlighted:bg-surface-card-hover data-highlighted:text-primary data-highlighted:outline-none cursor-pointer">
                            <Select.ItemText asChild>
                              <span className="block truncate min-w-0 max-w-full">{formatModelName(m)}</span>
                            </Select.ItemText>
                            <Select.ItemIndicator className="absolute left-1.5 inline-flex items-center justify-center">
                              <CheckIcon className="w-3.5 h-3.5" />
                            </Select.ItemIndicator>
                          </Select.Item>
                        ))}
                        {options.length > 0 && <Select.Separator className="h-px bg-subtle m-1" />}
                        <Select.Item value="__custom__" className="relative flex items-center pl-6 pr-3 py-2 text-xs font-mono text-primary rounded-[3px] select-none data-highlighted:bg-surface-card-hover data-highlighted:text-primary data-highlighted:outline-none cursor-pointer">
                          <Select.ItemText>Kustom…</Select.ItemText>
                          <Select.ItemIndicator className="absolute left-1.5 inline-flex items-center justify-center">
                            <CheckIcon className="w-3.5 h-3.5" />
                          </Select.ItemIndicator>
                        </Select.Item>
                      </Select.Viewport>
                      <Select.ScrollDownButton className="flex items-center justify-center h-6.25 bg-surface-card text-primary cursor-default">
                        <ChevronDownIcon className="w-3.5 h-3.5" />
                      </Select.ScrollDownButton>
                    </Select.Content>
                  </Select.Portal>
                </Select.Root>
              ) : (
                <div className="space-y-1">
                  <input
                    id="embModelNameInput"
                    type="text"
                    disabled={!!embeddingConfig?.locked || !targetConfigId}
                    placeholder="slug model"
                    value={embModelName}
                    onChange={(e) => setEmbModelName(e.target.value)}
                    className="minimal-input w-full px-3 py-2 rounded-md text-xs font-mono disabled:opacity-50"
                  />
                  <button
                    type="button"
                    onClick={() => setIsCustomModelInput(false)}
                    className="text-xs text-muted hover:text-primary underline cursor-pointer font-mono"
                  >
                    pilih dari daftar
                  </button>
                </div>
              )}
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label htmlFor="embDimensions" className="block text-xs font-mono uppercase tracking-wider text-muted">
                  DIMENSI
                </label>
                {probedDims && !embDimensions ? (
                  <span className="text-xs font-mono text-muted" title="Terdeteksi otomatis dari provider">
                    auto: {probedDims}
                  </span>
                ) : !embDimensions ? (
                  <span className="text-xs font-mono text-muted/50">opsional</span>
                ) : null}
              </div>
              <input
                id="embDimensions"
                type="number"
                disabled={!!embeddingConfig?.locked}
                placeholder={probedDims ? `auto (${probedDims})` : 'auto'}
                value={embDimensions === '' ? '' : embDimensions}
                onChange={(e) => setEmbDimensions(e.target.value === '' ? '' : parseInt(e.target.value) || '')}
                className="minimal-input w-full px-3 py-2 rounded-md text-xs font-mono disabled:opacity-50"
              />
            </div>
          </div>

          {embProvider === 'openai_compatible' ? (
            <div>
              <label htmlFor="embBaseUrl" className="block text-xs font-mono uppercase tracking-wider text-muted mb-1.5">
                BASE URL
              </label>
              <input
                id="embBaseUrl"
                type="url"
                disabled={!!embeddingConfig?.locked}
                placeholder="https://api.openai.com/v1"
                value={embBaseUrl}
                onChange={(e) => setEmbBaseUrl(e.target.value)}
                className="minimal-input w-full px-3 py-2 rounded-md text-xs font-mono disabled:opacity-50"
              />
            </div>
          ) : null}
        </div>

        <div className="flex-1" />


        <div className="flex justify-end pt-4 border-t border-subtle mt-auto">
          <button
            type="submit"
            disabled={!!embeddingConfig?.locked || isSavingEmbedding}
            className="minimal-button-primary px-4 py-2 rounded-md text-xs font-medium cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
          >
            {isSavingEmbedding ? (
              <>
                <span className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
                <span>Menyimpan…</span>
              </>
            ) : (
              <span>Simpan</span>
            )}
          </button>
        </div>
      </form>
    </section>
  );
}

export default EmbeddingSettingsSection;
