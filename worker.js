const wantsMarkdown = (request) =>
  (request.headers.get("accept") || "").includes("text/markdown");

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.endsWith("/") && wantsMarkdown(request)) {
      const mdPath = url.pathname + "index.md";
      const md = await env.ASSETS.fetch(new URL(mdPath, url), request);
      if (md.ok) {
        const headers = new Headers(md.headers);
        headers.set("content-type", "text/markdown; charset=utf-8");
        headers.set("content-location", mdPath);
        headers.set("vary", "Accept");
        return new Response(md.body, { status: md.status, headers });
      }
    }
    return env.ASSETS.fetch(request);
  },
};
