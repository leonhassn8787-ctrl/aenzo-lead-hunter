import { createClient } from "npm:@supabase/supabase-js@2.119.0";
const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { ...cors, "Content-Type": "application/json" } });

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  const auth = req.headers.get("Authorization") || "";
  if (!auth.startsWith("Bearer ")) return json({ error: "Sign-in required" }, 401);
  const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_ANON_KEY")!, {
    global: { headers: { Authorization: auth } },
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data: ud, error: ue } = await supabase.auth.getUser();
  if (ue || !ud.user) return json({ error: "Invalid session" }, 401);
  const owner_id = ud.user.id;

  if (req.method === "GET") {
    const url = new URL(req.url);
    const status = url.searchParams.get("status") || "new";
    const limit = Math.min(100, Math.max(1, Number(url.searchParams.get("limit") || 50)));
    const { data, error } = await supabase.from("discovery_candidates")
      .select("id,source_name,title,summary,evidence_url,published_at,signal_type,signal_score,review_status,created_at")
      .eq("owner_id", owner_id)
      .eq("review_status", status)
      .order("signal_score", { ascending: false })
      .order("created_at", { ascending: false })
      .limit(limit);
    if (error) return json({ error: error.message }, 400);
    const { data: runs } = await supabase.from("scan_runs")
      .select("id,status,started_at,finished_at,sources_checked,leads_found,leads_saved,error_summary")
      .eq("owner_id", owner_id).order("created_at", { ascending: false }).limit(5);
    return json({ candidates: data || [], recent_scans: runs || [] });
  }

  if (req.method !== "POST") return json({ error: "Use GET or POST" }, 405);
  let body: any;
  try { body = await req.json(); } catch { return json({ error: "Invalid JSON" }, 400); }
  const candidate_id = String(body.candidate_id || "");
  const action = String(body.action || "");
  if (!candidate_id || !["convert", "reject"].includes(action)) return json({ error: "candidate_id and action=convert|reject are required" }, 400);

  const { data: candidate, error: ce } = await supabase.from("discovery_candidates")
    .select("*").eq("id", candidate_id).eq("owner_id", owner_id).single();
  if (ce || !candidate) return json({ error: "Candidate not found" }, 404);
  if (candidate.review_status === "converted") return json({ error: "Already converted" }, 409);
  if (candidate.review_status === "rejected") return json({ error: "Already rejected" }, 409);

  if (action === "reject") {
    const { error } = await supabase.from("discovery_candidates")
      .update({ review_status: "rejected" }).eq("id", candidate_id).eq("owner_id", owner_id);
    if (error) return json({ error: error.message }, 400);
    return json({ success: true, action: "rejected", candidate_id });
  }

  const company_name = String(body.company_name || candidate.title).trim().slice(0, 250);
  const industry = String(body.industry || "Web3 / Crypto").trim().slice(0, 120);
  const service_need = String(body.service_need || candidate.summary || "Needs manual qualification; no confirmed service request yet.").trim().slice(0, 3000);
  const lead_type = ["direct_buyer", "potential_buyer", "partnership_opportunity"].includes(body.lead_type) ? body.lead_type : "potential_buyer";
  const contacts = Array.isArray(body.contacts) ? body.contacts.slice(0, 30) : [];
  const dedupe_key = candidate.evidence_url.split("?")[0].replace(/\/$/, "").toLowerCase();
  const rawScore = Number(body.priority_score ?? candidate.signal_score ?? 30);
  if (!Number.isInteger(rawScore) || rawScore < 1 || rawScore > 100) return json({ error: "priority_score must be an integer from 1 to 100" }, 400);

  const lead = {
    owner_id, company_name, website: body.website || null, industry, service_need, lead_type,
    priority_score: rawScore,
    status: "new", evidence_summary: candidate.summary || candidate.title,
    evidence_url: candidate.evidence_url,
    evidence_date: candidate.published_at ? candidate.published_at.slice(0, 10) : new Date().toISOString().slice(0, 10),
    telegram_group_url: body.telegram_group_url || null,
    contacts, outreach_english: body.outreach_english || null,
    outreach_bengali: body.outreach_bengali || null,
    notes: "Promoted from discovery candidate. Verify buyer intent and public contacts before outreach.",
    dedupe_key,
  };
  const { data: existing } = await supabase.from("leads").select("id").eq("owner_id", owner_id).eq("dedupe_key", dedupe_key).maybeSingle();
  if (existing) return json({ error: "This evidence is already present in Leads", existing_lead_id: existing.id }, 409);
  const { data: inserted, error: ie } = await supabase.from("leads").insert(lead).select("id,company_name,lead_type,status").single();
  if (ie) return json({ error: ie.message }, 400);
  const { error: updateError } = await supabase.from("discovery_candidates")
    .update({ review_status: "converted" }).eq("id", candidate_id).eq("owner_id", owner_id);
  if (updateError) return json({ success: true, lead: inserted, warning: "Lead saved but candidate status update failed: " + updateError.message }, 200);
  return json({ success: true, action: "converted", lead: inserted, note: "The article signal is not proof of a confirmed buyer. Complete contact and need verification before outreach." });
});
