'use client';

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import {
  fetchSSEStream,
  getSessionMessages,
  listChatSessions,
  deleteChatSession,
} from '@/lib/api';
import type { ChatMessage, ChatSession, Citation } from '@/types';
import { useApp } from './AppContext';
import { useDocument } from './DocumentContext';

function createChatMessage(id: string, sender: 'user' | 'assistant', content: string): ChatMessage {
  return { id, sender, content, citations: [], created_at: new Date().toISOString() };
}

interface ChatContextType {
  sessions: ChatSession[];
  activeSessionId: string | null;
  messages: ChatMessage[];
  isStreaming: boolean;
  isInitializingSessions: boolean;
  selectedCitation: Citation | null;
  setSelectedCitation: (citation: Citation | null) => void;
  handleNewChat: () => void;
  handleSelectSession: (sessionId: string) => Promise<void>;
  handleDeleteSession: (sessionId: string) => Promise<void>;
  handleSendMessage: (query: string) => Promise<void>;
}

const ChatContext = createContext<ChatContextType | null>(null);

export function ChatProvider({ children }: { readonly children: React.ReactNode }) {
  const { token, provider } = useApp();
  const { activeDocuments } = useDocument();

  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [fetchedTokenSessions, setFetchedTokenSessions] = useState<string | null>(null);

  const isInitializingSessions = token !== fetchedTokenSessions;

  const reloadSessions = useCallback(async (accessToken: string) => {
    const res = await listChatSessions(accessToken);
    if (res.success && res.data) {
      setSessions(res.data);
      return res.data;
    }
    return [];
  }, []);

  const loadSessionMessages = useCallback(async (sessionId: string, accessToken: string) => {
    if (!sessionId || !accessToken) return;
    setActiveSessionId(sessionId);
    const res = await getSessionMessages(sessionId, accessToken);
    if (res.success && res.data) {
      setMessages(res.data);
    } else {
      console.error('Gagal memuat pesan sesi:', res.error);
    }
  }, []);

  useEffect(() => {
    if (token) {
      reloadSessions(token).finally(() => setFetchedTokenSessions(token));
    } else {
      setSessions([]);
      setActiveSessionId(null);
      setMessages([]);
      setFetchedTokenSessions(null);
    }
  }, [token, reloadSessions]);

  const handleNewChat = useCallback(() => {
    setActiveSessionId(null);
    setMessages([]);
    setSelectedCitation(null);
  }, []);

  const handleSelectSession = useCallback(async (sessionId: string) => {
    if (!token) return;
    setSelectedCitation(null);
    await loadSessionMessages(sessionId, token);
  }, [token, loadSessionMessages]);

  const handleDeleteSession = useCallback(async (sessionId: string) => {
    if (!token) return;
    const res = await deleteChatSession(sessionId, token);
    if (res.success) {
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (activeSessionId === sessionId) {
        handleNewChat();
      }
    }
  }, [token, activeSessionId, handleNewChat]);

  const updateAssistantMessage = useCallback((assistantId: string, update: Partial<ChatMessage>) => {
    setMessages((prev) =>
      prev.map((msg) => (msg.id === assistantId ? { ...msg, ...update } : msg))
    );
  }, []);

  const handleSendMessage = useCallback(async (query: string) => {
    if (!token) return;

    const assistantId = `assistant-${Date.now()}`;
    const userMsg = createChatMessage(`user-${Date.now()}`, 'user', query);
    const assistantMsg = createChatMessage(assistantId, 'assistant', '');

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);

    let accumulatedTokens = '';
    let rafId = 0;
    const flushTokens = () => {
      rafId = 0;
      updateAssistantMessage(assistantId, { content: accumulatedTokens });
    };

    const activeDocIds = activeDocuments.map((d) => d.id);

    await fetchSSEStream(
      query,
      token,
      provider,
      activeDocIds,
      {
        onSession: (sessId) => {
          setActiveSessionId(sessId);
          reloadSessions(token);
        },
        onCitations: (citations) => updateAssistantMessage(assistantId, { citations }),
        onToken: (tokenText) => {
          accumulatedTokens += tokenText;
          if (!rafId) rafId = requestAnimationFrame(flushTokens);
        },
        onComplete: () => {
          if (rafId) { cancelAnimationFrame(rafId); flushTokens(); }
          setIsStreaming(false);
          reloadSessions(token);
        },
        onError: (errorMsg) => {
          if (rafId) cancelAnimationFrame(rafId);
          updateAssistantMessage(assistantId, { content: `Error: ${errorMsg}` });
          setIsStreaming(false);
        },
      },
      activeSessionId || undefined
    );
  }, [token, provider, activeDocuments, activeSessionId, updateAssistantMessage, reloadSessions]);

  const value = useMemo(
    () => ({
      sessions,
      activeSessionId,
      messages,
      isStreaming,
      selectedCitation,
      isInitializingSessions,
      setSelectedCitation,
      handleNewChat,
      handleSelectSession,
      handleDeleteSession,
      handleSendMessage,
    }),
    [
      sessions,
      activeSessionId,
      messages,
      isStreaming,
      selectedCitation,
      isInitializingSessions,
      handleNewChat,
      handleSelectSession,
      handleDeleteSession,
      handleSendMessage,
    ]
  );

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChat() {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error('useChat must be used within a ChatProvider');
  }
  return context;
}
