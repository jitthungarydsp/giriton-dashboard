import * as routeQualityApi from "./functions/api/route-quality.js";
import * as sessionApi from "./functions/api/session.js";
import * as vehiclesApi from "./functions/api/vehicles.js";

const routes = {
  "/api/route-quality": routeQualityApi,
  "/api/session": sessionApi,
  "/api/vehicles": vehiclesApi
};

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store"
    }
  });
}

function methodHandler(module, method) {
  const suffix = method.charAt(0).toUpperCase() + method.slice(1).toLowerCase();
  return module?.[`onRequest${suffix}`];
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const module = routes[url.pathname];
    if (module) {
      const handler = methodHandler(module, request.method);
      if (!handler) return json({ error: "Method not allowed" }, 405);
      return handler({ request, env, ctx });
    }
    return env.ASSETS.fetch(request);
  }
};
