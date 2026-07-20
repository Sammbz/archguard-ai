import { createBrowserClient } from '@supabase/ssr'

/** Client Supabase pour les Client Components. Clé anonyme uniquement :
 *  c'est le RLS, côté base, qui restreint l'accès aux données. */
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  )
}
