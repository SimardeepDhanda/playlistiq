"use client";

import { useEffect, useState } from "react";
import { api } from "./api";
import type { AuthState } from "./types";

const SIGNED_OUT: AuthState = { spotify_configured: false, connected: false, display_name: null };

/** Who is signed in. `null` while loading. */
export function useAuth(): AuthState | null {
  const [auth, setAuth] = useState<AuthState | null>(null);
  useEffect(() => {
    api
      .me()
      .then(setAuth)
      .catch(() => setAuth(SIGNED_OUT));
  }, []);
  return auth;
}
