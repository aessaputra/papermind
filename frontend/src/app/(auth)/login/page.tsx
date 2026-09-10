'use client';

import { useAuth } from '@/hooks/useAuth';
import { AuthError, AuthForm, AuthHeader } from '@/components/auth/AuthForm';

export default function LoginPage() {
  const {
    email,
    password,
    authState,
    setEmail,
    setPassword,
    handleSubmit,
  } = useAuth('signin');

  return (
    <>
      <AuthHeader mode="signin" />
      <AuthError message={authState.status === 'error' ? authState.message : undefined} />
      <AuthForm
        mode="signin"
        email={email}
        setEmail={setEmail}
        password={password}
        setPassword={setPassword}
        authState={authState}
        onSubmit={handleSubmit}
      />
    </>
  );
}
