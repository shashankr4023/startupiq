import { createClient } from "@supabase/supabase-js";

// The browser Supabase client. It handles login, stores the session (incl. the
// JWT access token) in the browser, and refreshes it automatically. The anon
// key is safe to expose to the browser - it only allows what Supabase's auth +
// row-level-security rules permit.
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
