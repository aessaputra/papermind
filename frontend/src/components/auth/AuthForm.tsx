import Link from 'next/link';
import type { AuthMode } from '@/hooks/useAuth';
import type { AuthState } from '@/types';

export function AuthHeader({ mode }: { mode: AuthMode }) {
  const isSignIn = mode === 'signin';
  const title = isSignIn ? 'Masuk' : 'Daftar';

  return (
    <div className="flex items-baseline justify-between border-b border-subtle pb-4">
      <h1 className="font-serif text-3xl font-semibold tracking-tight text-primary">
        {title}
      </h1>

      <div className="flex items-center gap-1.5 text-xs font-mono">
        <span className="text-muted">{isSignIn ? 'Belum punya akun?' : 'Sudah punya akun?'}</span>
        <Link
          href={isSignIn ? '/register' : '/login'}
          className="text-primary hover:text-secondary underline underline-offset-4 transition-colors duration-150"
        >
          {isSignIn ? 'Daftar' : 'Masuk'}
        </Link>
      </div>
    </div>
  );
}

export function AuthError({ message }: { message?: string }) {
  if (!message) return null;

  return (
    <div className="p-3 rounded-md bg-(--pastel-red-bg) border border-(--pastel-red-text)/20 text-(--pastel-red-text) text-xs leading-normal">
      {message}
    </div>
  );
}

interface AuthFormProps {
  mode: AuthMode;
  email: string;
  setEmail: (v: string) => void;
  password: string;
  setPassword: (v: string) => void;
  authState: AuthState;
  onSubmit: (e: React.SyntheticEvent<HTMLFormElement>) => void;
}

export function AuthForm({
  mode,
  email,
  setEmail,
  password,
  setPassword,
  authState,
  onSubmit,
}: AuthFormProps) {
  const isLoading = authState.status === 'loading';
  const buttonLabel = mode === 'signin' ? 'Masuk' : 'Daftar';
  const autoComplete = mode === 'signup' ? 'new-password' : 'current-password';

  return (
    <form onSubmit={onSubmit} className="space-y-4" autoComplete="on">
      <div>
        <label
          htmlFor="auth-email"
          className="block font-mono text-xs uppercase tracking-wider text-muted mb-1.5"
        >
          EMAIL
        </label>
        <input
          id="auth-email"
          name="email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="nama@email.com"
          className="w-full px-3 py-3 md:py-2.5 rounded-md minimal-input text-xs"
        />
      </div>

      <div>
        <label
          htmlFor="auth-password"
          className="block font-mono text-xs uppercase tracking-wider text-muted mb-1.5"
        >
          KATA SANDI
        </label>
        <input
          id="auth-password"
          name="password"
          type="password"
          autoComplete={autoComplete}
          required
          minLength={6}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
          className="w-full px-3 py-3 md:py-2.5 rounded-md minimal-input text-xs"
        />
      </div>

      <button
        type="submit"
        disabled={isLoading}
        className="w-full mt-2 py-3 md:py-2.5 px-4 rounded-md minimal-button-primary text-xs flex items-center justify-center cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isLoading ? (
          <span className="flex items-center gap-2">
            <span className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
            Memproses…
          </span>
        ) : (
          <span>{buttonLabel}</span>
        )}
      </button>
    </form>
  );
}
