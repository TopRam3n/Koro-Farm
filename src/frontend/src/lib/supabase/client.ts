import { createBrowserClient } from "@supabase/ssr";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
const demoMode = process.env.NEXT_PUBLIC_APP_MODE === "demo" || process.env.NEXT_PUBLIC_AUTH_MODE === "demo";

export const createClient = () =>
  createBrowserClient(
    supabaseUrl ?? (demoMode ? "http://127.0.0.1:3000" : ""),
    supabaseKey ?? (demoMode ? "sb_publishable_My-sQg312mbIE2RnZrQ08Q_fSijD3fR" : ""),
  );
