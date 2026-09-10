'use client';

import { useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { createClient } from '@/lib/supabaseClient';
import { isNetworkError } from '@/lib/utils';
import type { AuthState } from '@/types';

function toUserFriendlyError(message: string): string {
  if (isNetworkError(message)) {
    return 'Gagal terhubung ke server otentikasi. Periksa koneksi internet Anda.';
  }
  return message;
}

export type AuthMode = 'signin' | 'signup';

export function useAuth(mode: AuthMode) {
  const router = useRouter();
  const supabase = useMemo(() => createClient(), []);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [authState, setAuthState] = useState<AuthState>({ status: 'idle' });

  const handleSubmit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();

    if (!email || !password) return;

    setAuthState({ status: 'loading' });

    try {
      const authAction =
        mode === 'signup'
          ? supabase.auth.signUp({ email, password })
          : supabase.auth.signInWithPassword({ email, password });

      const { data, error } = await authAction;
      if (error) throw error;

      if (data.user) {
        setAuthState({ status: 'success' });
        router.refresh();
        router.push('/');
      }
    } catch (err: any) {
      console.error('Auth error:', err);
      setAuthState({
        status: 'error',
        message: toUserFriendlyError(err.message || 'Otentikasi gagal.'),
      });
    }
  };

  return {
    email,
    password,
    authState,
    setEmail,
    setPassword,
    handleSubmit,
  };
}
