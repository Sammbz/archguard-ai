'use server'

import { revalidatePath } from 'next/cache'
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'

export async function createProject(formData: FormData) {
  const supabase = await createClient()

  // Les Server Actions sont joignables par POST direct : on revérifie
  // l'authentification ici, sans se reposer sur le proxy.
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) redirect('/login')

  const name = String(formData.get('name') ?? '').trim()
  if (!name) return

  const { error } = await supabase.from('projects').insert({
    owner_id: user.id,
    name,
    description: String(formData.get('description') ?? '').trim() || null,
    project_type: String(formData.get('project_type') ?? '').trim() || null,
    location: String(formData.get('location') ?? '').trim() || null,
  })
  if (error) throw new Error(error.message)

  revalidatePath('/projects')
}

export async function signOut() {
  const supabase = await createClient()
  await supabase.auth.signOut()
  redirect('/login')
}
