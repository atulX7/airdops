"use client"

import type { ReactNode } from "react"

const localSession = {
  user: {
    id: "00000000-0000-0000-0000-000000000001",
    name: "Local User",
    email: "local@airdops.local",
    image: null,
    roles: ["owner", "admin"],
    workspace_ids: [] as string[],
  },
  expires: "2099-12-31T23:59:59.999Z",
}

export function SessionProvider({ children }: { children: ReactNode }) {
  return <>{children}</>
}

export function useSession() {
  return {
    data: localSession,
    status: "authenticated" as const,
    update: async () => localSession,
  }
}

export async function signIn() {
  return { ok: true, error: null, status: 200, url: "/dashboard" }
}

export async function signOut() {
  if (typeof window !== "undefined") {
    window.location.href = "/dashboard"
  }
}

export function getSession() {
  return Promise.resolve(localSession)
}

export function getCsrfToken() {
  return Promise.resolve("")
}

export function getProviders() {
  return Promise.resolve({})
}
