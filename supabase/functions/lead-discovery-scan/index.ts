import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

Deno.serve((req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  return new Response(JSON.stringify({
    error: "The legacy RSS discovery scanner has been retired.",
    message: "AENZO lead discovery now uses only the Telegram group worker. It scans groups already joined by the connected Telegram account. No external websites, directories, RSS feeds, or non-joined groups are searched.",
    workflow: "https://github.com/leonhassn8787-ctrl/aenzo-lead-hunter/actions/workflows/telegram-scan.yml"
  }), {
    status: 410,
    headers: { ...cors, "Content-Type": "application/json" },
  });
});
