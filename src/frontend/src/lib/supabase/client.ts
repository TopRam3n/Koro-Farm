import { createBrowserClient } from "@supabase/ssr";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
const demoMode = process.env.NEXT_PUBLIC_APP_MODE === "demo" || process.env.NEXT_PUBLIC_AUTH_MODE === "demo";

export const createClient = () =>
  createBrowserClient(
    supabaseUrl ?? (demoMode ? "http://127.0.0.1:54321" : ""),
    supabaseKey ?? (demoMode ? "demo-public-key" : ""),
  );
