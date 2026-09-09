export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);
    if (incoming.protocol !== "https:") {
      incoming.protocol = "https:";
      return Response.redirect(incoming, 308);
    }

    let upstream;
    let path = incoming.pathname;
    const isApi = path === "/api" || path.startsWith("/api/");
    if (isApi) {
      if (!env.GATEWAY_SECRET) {
        return new Response("Service unavailable", { status: 503 });
      }
      upstream = new URL(env.API_ORIGIN);
    } else if (path === "/admin" || path.startsWith("/admin/")) {
      upstream = new URL(env.ADMIN_ORIGIN);
      path = path === "/admin" ? "/" : path.slice("/admin".length);
    } else {
      upstream = new URL(env.TEACHER_ORIGIN);
    }
    upstream.pathname = path;
    upstream.search = incoming.search;
    const headers = new Headers(request.headers);
    headers.delete("x-flrc-gateway");
    if (isApi) {
      headers.set("x-flrc-gateway", env.GATEWAY_SECRET);
    }
    headers.set("x-forwarded-host", incoming.host);
    headers.set("x-forwarded-proto", incoming.protocol.slice(0, -1));
    const upstreamResponse = await fetch(upstream, {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
      redirect: "manual",
    });
    const response = new Response(upstreamResponse.body, upstreamResponse);
    response.headers.delete("server");
    response.headers.set("Strict-Transport-Security", "max-age=31536000; includeSubDomains");
    response.headers.set("X-Content-Type-Options", "nosniff");
    response.headers.set("X-Frame-Options", "DENY");
    response.headers.set("Referrer-Policy", "no-referrer");
    response.headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
    response.headers.set("Cross-Origin-Resource-Policy", "same-origin");
    if (isApi) {
      response.headers.set("Cache-Control", "no-store, private, max-age=0");
      response.headers.set("Pragma", "no-cache");
    } else if (request.headers.get("sec-fetch-mode") === "navigate") {
      response.headers.set("Cache-Control", "no-store, max-age=0");
    }
    return response;
  },
};
