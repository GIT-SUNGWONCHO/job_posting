import { createClient, type SupabaseClient } from '@supabase/supabase-js'

// 브라우저에는 Supabase 주소와 공개 키만 둔다. 데이터는 로그인과 행 단위 권한으로 막는다.
const url = import.meta.env.VITE_SUPABASE_URL as string | undefined
const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string | undefined

export const supabase: SupabaseClient | null = url && publishableKey ? createClient(url, publishableKey) : null

export const SCREEN_BUCKET = 'screen'
export const SCREEN_PATH = 'screen.json.gz'
