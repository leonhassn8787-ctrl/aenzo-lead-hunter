import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

Deno.serve((req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  return new Response(JSON.stringify({
    error: "The legacy external-discovery review endpoint has been retired.",
    message: "AENZO Lead Hunter now accepts automated leads only from Telegram groups already joined by the connected account. Existing historical discovery records remain stored but cannot be promoted through this retired endpoint.",
    workflow: "https://github.com/leonhassn8787-ctrl/aenzo-lead-hunter/actions/workflows/telegram-scan.yml"
  }), {
    status: 410,
    headers: { ...cors, "Content-Type": "application/json" },
  });
});
