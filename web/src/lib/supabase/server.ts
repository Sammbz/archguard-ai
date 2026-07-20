import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'

/** Client Supabase pour les Server Components et Server Actions.
 *  `cookies()` est asynchrone depuis Next.js 16. */
export async function createClient() {
  const cookieStore = await cookies()

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll()
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options)
            )
          } catch {
            // Appelé depuis un Server Component : le rafraîchissement de
            // session est déjà assuré par proxy.ts, on peut ignorer.
          }
        },
      },
    }
  )
}
