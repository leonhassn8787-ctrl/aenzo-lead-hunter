import { createClient } from "npm:@supabase/supabase-js@2.119.0";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Content-Type": "application/json",
};

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (!["GET", "POST"].includes(req.method)) {
    return new Response(JSON.stringify({ error: "Method not allowed" }), { status: 405, headers: cors });
  }

  const authHeader = req.headers.get("Authorization");
  if (!authHeader) return new Response(JSON.stringify({ error: "Authentication required" }), { status: 401, headers: cors });

  const supabase = createClient(
    Deno.env.get("SUPABASE_URL") ?? "",
    Deno.env.get("SUPABASE_ANON_KEY") ?? "",
    { global: { headers: { Authorization: authHeader } }, auth: { persistSession: false } }
  );

  const token = authHeader.replace(/^Bearer\s+/i, "");
  const { data: authData, error: authError } = await supabase.auth.getUser(token);
  if (authError || !authData.user) return new Response(JSON.stringify({ error: "Invalid session" }), { status: 401, headers: cors });

  if (req.method === "GET") {
    const { data, error } = await supabase
      .from("lead_sources")
      .select("id, source_name, source_type, source_url, is_active, notes, last_checked_at, created_at")
      .order("source_name", { ascending: true });
    if (error) return new Response(JSON.stringify({ error: "Could not load sources" }), { status: 500, headers: cors });
    return new Response(JSON.stringify({ ok: true, count: data.length, sources: data }), { status: 200, headers: cors });
  }

  let body: { id?: string; is_active?: boolean };
  try { body = await req.json(); } catch {
    return new Response(JSON.stringify({ error: "Invalid JSON" }), { status: 400, headers: cors });
  }
  if (!body.id || typeof body.is_active !== "boolean") {
    return new Response(JSON.stringify({ error: "Provide source id and is_active boolean" }), { status: 400, headers: cors });
  }
  const { data, error } = await supabase
    .from("lead_sources")
    .update({ is_active: body.is_active })
    .eq("id", body.id)
    .select("id, source_name, is_active")
    .maybeSingle();
  if (error) return new Response(JSON.stringify({ error: "Could not update source" }), { status: 500, headers: cors });
  if (!data) return new Response(JSON.stringify({ error: "Source not found" }), { status: 404, headers: cors });
  return new Response(JSON.stringify({ ok: true, source: data }), { status: 200, headers: cors });
});
