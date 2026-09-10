'use client';

import React, { useEffect, useRef } from 'react';
import Link from 'next/link';
import { ArrowUpIcon, FileTextIcon, LockClosedIcon, GearIcon, MagicWandIcon } from '@radix-ui/react-icons';
import { useApp } from '@/context/AppContext';
import { useDocument } from '@/context/DocumentContext';
import { useChat } from '@/context/ChatContext';
import { ChatMessageItem } from './ChatMessageItem';

const SUGGESTION_PROMPTS = [
  'Buat ringkasan dari dokumen ini.',
  'Adakah informasi penting yang perlu saya perhatikan?',
  'Apa kesimpulan utama dari dokumen ini?',
];

interface ChatWindowMessagesProps {
  readonly onSetInputQuery: (text: string) => void;
}

function ChatWindowMessages({ onSetInputQuery }: ChatWindowMessagesProps) {
  const { hasCredentials } = useApp();
  const { activeDocumentCount, setIsDocModalOpen } = useDocument();
  const { messages, isStreaming, setSelectedCitation } = useChat();

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: isStreaming ? 'auto' : 'smooth' });
  }, [messages, isStreaming]);

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4 md:space-y-6">
      {!hasCredentials ? (
        <div className="h-full flex flex-col items-center justify-center text-center p-8 max-w-xs mx-auto">
          <div className="w-10 h-10 rounded-md bg-surface-card border border-subtle flex items-center justify-center mb-4">
            <LockClosedIcon className="w-4 h-4 text-muted" aria-hidden="true" />
          </div>
          <h2 className="text-base font-serif font-semibold text-primary mb-1.5">
            Konfigurasi Kunci API
          </h2>
          <p className="text-sm text-muted mb-4 leading-normal">
            Minta LLM Anda untuk memecahkan masalah.
          </p>
          <div className="mt-4">
            <Link
              href="/settings"
              className="text-xs font-mono minimal-button-secondary px-3 py-1.5 rounded-sm inline-flex items-center hover:bg-surface-hover transition-colors gap-1.5 focus-visible:ring-2 focus-visible:ring-zinc-400"
            >
              <GearIcon className="w-3.5 h-3.5" aria-hidden="true" />
              <span>Pengaturan</span>
            </Link>
          </div>
        </div>
      ) : messages.length === 0 ? (
        <div className="h-full flex flex-col items-center justify-center text-center py-16 max-w-md mx-auto">
          {activeDocumentCount === 0 ? (
            <>
              <div className="p-3.5 rounded-full bg-surface-card border border-subtle mb-4 text-muted">
                <FileTextIcon className="w-6 h-6" aria-hidden="true" />
              </div>
              <h2 className="text-xl font-serif font-semibold text-primary tracking-tight text-balance mb-5">
                Tidak ada dokumen aktif
              </h2>
              <button
                type="button"
                onClick={() => setIsDocModalOpen(true)}
                className="minimal-button-primary py-2 px-4 rounded-md text-xs font-medium flex items-center gap-2 cursor-pointer"
              >
                <FileTextIcon className="w-3.5 h-3.5" aria-hidden="true" />
                <span>Kelola Dokumen</span>
              </button>
            </>
          ) : (
            <>
              <div className="p-3.5 rounded-full bg-surface-card border border-subtle mb-4 text-muted">
                <MagicWandIcon className="w-6 h-6" aria-hidden="true" />
              </div>
              <h2 className="text-2xl font-serif font-semibold text-primary tracking-tight mb-6">
                Dari mana sebaiknya kita mulai?
              </h2>


              <div className="flex flex-col gap-2 w-full">
                {SUGGESTION_PROMPTS.map((promptText, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => onSetInputQuery(promptText)}
                    className="w-full text-left p-3 rounded-lg bg-surface-card hover:bg-surface-card-hover border border-subtle text-sm text-secondary hover:text-primary transition-all cursor-pointer flex items-center justify-between group"
                  >
                    <span>{promptText}</span>
                    <ArrowUpIcon className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity text-muted" />
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      ) : (
        messages.map((msg) => (
          <ChatMessageItem
            key={msg.id}
            msg={msg}
            onSelectCitation={setSelectedCitation}
          />
        ))
      )}
      <div ref={messagesEndRef} />
    </div>
  );
}

export default ChatWindowMessages;
