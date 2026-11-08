import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2.119.0";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

function reply(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "GET" && req.method !== "POST") return reply({ error: "Method not allowed" }, 405);

  const authHeader = req.headers.get("Authorization");
  if (!authHeader?.startsWith("Bearer ")) return reply({ error: "Sign in required" }, 401);

  const url = Deno.env.get("SUPABASE_URL");
  const key =
    Deno.env.get("SUPABASE_ANON_KEY") ??
    Deno.env.get("SUPABASE_PUBLISHABLE_KEY") ??
    (() => {
      const raw = Deno.env.get("SUPABASE_PUBLISHABLE_KEYS");
      if (!raw) return undefined;
      try {
        const keys = JSON.parse(raw);
        return keys.default ? Deno.env.get(keys.default) : undefined;
      } catch {
        return undefined;
      }
    })();

  if (!url || !key) return reply({ error: "Supabase environment is not configured" }, 500);

  const supabase = createClient(url, key, {
    global: { headers: { Authorization: authHeader } },
    auth: { persistSession: false, autoRefreshToken: false },
  });

  const token = authHeader.slice("Bearer ".length);
  const { data: authData, error: authError } = await supabase.auth.getUser(token);
  if (authError || !authData.user) return reply({ error: "Invalid or expired session" }, 401);
  const owner_id = authData.user.id;

  if (req.method === "GET") {
    const { data, error } = await supabase
      .from("leads")
      .select("id,company_name,website,industry,service_need,lead_type,priority_score,status,evidence_summary,evidence_url,evidence_date,telegram_group_url,contacts,outreach_english,outreach_bengali,notes,created_at")
      .eq("owner_id", owner_id)
      .order("priority_score", { ascending: false })
      .order("created_at", { ascending: false })
      .limit(1000);
    if (error) return reply({ error: "Could not load leads", details: error.message }, 500);
    return reply({ ok: true, count: data.length, leads: data });
  }

  let input: Record<string, unknown>;
  try {
    input = await req.json();
  } catch {
    return reply({ error: "Request body must be valid JSON" }, 400);
  }

  const company_name = typeof input.company_name === "string" ? input.company_name.trim() : "";
  if (!company_name) return reply({ error: "company_name is required" }, 400);

  const leadTypes = ["direct_buyer", "potential_buyer", "partnership_opportunity"];
  const lead_type = leadTypes.includes(String(input.lead_type)) ? String(input.lead_type) : "potential_buyer";
  const score = Number(input.priority_score ?? 50);
  if (!Number.isInteger(score) || score < 1 || score > 100) return reply({ error: "priority_score must be an integer from 1 to 100" }, 400);

  const cleanText = (v: unknown, max = 4000) =>
    typeof v === "string" && v.trim() ? v.trim().slice(0, max) : null;

  const dedupe_key = cleanText(input.dedupe_key, 500);
  if (dedupe_key) {
    const { data: existing, error: lookupError } = await supabase
      .from("leads").select("id,company_name").eq("owner_id", owner_id).eq("dedupe_key", dedupe_key).maybeSingle();
    if (lookupError) return reply({ error: "Duplicate check failed", details: lookupError.message }, 500);
    if (existing) return reply({ ok: true, duplicate: true, lead: existing }, 200);
  }

  const row = {
    owner_id,
    company_name: company_name.slice(0, 300),
    website: cleanText(input.website, 1000),
    industry: cleanText(input.industry, 200),
    service_need: cleanText(input.service_need, 2000),
    lead_type,
    priority_score: score,
    status: "new",
    evidence_summary: cleanText(input.evidence_summary, 4000),
    evidence_url: cleanText(input.evidence_url, 2000),
    evidence_date: cleanText(input.evidence_date, 30),
    telegram_group_url: cleanText(input.telegram_group_url, 1000),
    contacts: Array.isArray(input.contacts) ? input.contacts.slice(0, 30) : [],
    outreach_english: cleanText(input.outreach_english, 4000),
    outreach_bengali: cleanText(input.outreach_bengali, 4000),
    notes: cleanText(input.notes, 4000),
    dedupe_key,
  };

  const { data: inserted, error: insertError } = await supabase.from("leads").insert(row).select("id,company_name,lead_type,priority_score,status,created_at").single();
  if (insertError) return reply({ error: "Lead could not be saved", details: insertError.message }, 500);
  return reply({ ok: true, duplicate: false, lead: inserted }, 201);
});
