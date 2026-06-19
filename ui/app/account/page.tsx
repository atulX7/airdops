"use client"

import { useEffect, useState } from "react"

interface User {
  id: string
  email: string
  name: string
  roles: string[]
  picture_url?: string
}

interface Workspace {
  id: string
  name: string
  role: string
  created_at: string
}

export default function AccountPage() {
  const [user, setUser] = useState<User | null>(null)
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchUser = async () => {
      setLoading(true)
      try {
        const res = await fetch("/api/v1/users/me")
        if (res.ok) {
          const data = await res.json()
          setUser(data)
        }
      } catch (e) {
        console.error("Failed to fetch user:", e)
      }
      setLoading(false)
    }
    fetchUser()
  }, [])

  return <div>Account Page</div>
}
