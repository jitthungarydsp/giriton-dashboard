function json(payload, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      ...extraHeaders
    }
  });
}

function readToken(request) {
  return String(request.headers.get("x-hub-report-token") || "").trim();
}

export async function onRequestPost({ request, env }) {
  const expected = String(env.HUB_REPORT_TOKEN || "").trim();
  const actual = readToken(request);
  if (!expected || !actual || actual !== expected) return json({ error: "Unauthorized" }, 401);

  const secure = new URL(request.url).protocol === "https:" ? "; Secure" : "";
  return json(
    { ok: true },
    200,
    {
      "set-cookie": `hub_report_token=${encodeURIComponent(actual)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000${secure}`
    }
  );
}

export async function onRequestDelete() {
  return json(
    { ok: true },
    200,
    {
      "set-cookie": "hub_report_token=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0; Secure"
    }
  );
}
