'use client';

import React from 'react';
import type { DocumentItem } from '@/types';
import { DocumentItemRow } from './DocumentItemRow';

interface DocumentListProps {
  documents: DocumentItem[];
  actionDocId: string | null;
  onToggleActive: (doc: DocumentItem) => Promise<void>;
  onPreview: (docId: string) => Promise<void>;
  onDelete: (docId: string) => Promise<void>;
}

export function DocumentList({
  documents,
  actionDocId,
  onToggleActive,
  onPreview,
  onDelete,
}: DocumentListProps) {
  return (
    <div className="space-y-2">
      <h3 className="text-xs font-mono font-medium uppercase tracking-wider text-muted px-1">
        DAFTAR DOKUMEN
      </h3>

      {documents.length === 0 ? (
        <div className="text-center py-8 text-xs text-muted border border-subtle rounded-lg">
          Belum ada dokumen yang diunggah.
        </div>
      ) : (
        <div className="space-y-2 max-h-80 overflow-y-auto pr-1 content-visibility-list">
          {documents.map((doc) => (
            <DocumentItemRow
              key={doc.id}
              doc={doc}
              isBusy={actionDocId === doc.id}
              onToggleActive={onToggleActive}
              onPreview={onPreview}
              onDelete={onDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}
