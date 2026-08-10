import { NextRequest } from "next/server";
import { fetch as undiciFetch, Agent } from "undici";

// Pass-through SSE vers omr-service — chunks relayés immédiatement
// (ne pas retourner res.body undici tel quel : Next peut bufferiser).
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 600;

const OMR_SERVICE_URL = process.env.OMR_SERVICE_URL ?? "http://localhost:8000";

const dispatcher = new Agent({
  headersTimeout: 600_000,
  bodyTimeout: 600_000,
  // Évite de garder des connexions idle trop longtemps pendant OCR/Audiveris.
  keepAliveTimeout: 600_000,
  keepAliveMaxTimeout: 600_000,
});

const SSE_HEADERS: HeadersInit = {
  "Content-Type": "text/event-stream; charset=utf-8",
  "Cache-Control": "no-cache, no-store, no-transform",
  Connection: "keep-alive",
  "X-Accel-Buffering": "no",
};

function sseError(detail: string, status = 502): Response {
  const payload = JSON.stringify({ detail });
  // Même media type : le client parsePdfStream lit aussi les erreurs JSON
  // si !res.ok — mais si on a déjà ouvert le stream on émet un event error.
  return new Response(payload, {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export async function POST(req: NextRequest) {
  const contentType = req.headers.get("content-type") ?? "application/octet-stream";
  const body = Buffer.from(await req.arrayBuffer());

  let upstream: Awaited<ReturnType<typeof undiciFetch>>;
  try {
    upstream = await undiciFetch(`${OMR_SERVICE_URL}/pdf/parse/stream`, {
      method: "POST",
      headers: {
        "content-type": contentType,
        Accept: "text/event-stream",
      },
      body,
      dispatcher,
    });
  } catch {
    return sseError(`service OMR injoignable (${OMR_SERVICE_URL})`);
  }

  if (!upstream.ok) {
    const text = await upstream.text();
    let detail = `HTTP ${upstream.status}`;
    try {
      detail = (JSON.parse(text) as { detail?: string }).detail ?? text;
    } catch {
      if (text) detail = text.slice(0, 500);
    }
    return sseError(detail, upstream.status);
  }

  if (!upstream.body) {
    return sseError("réponse vide du service OMR");
  }

  const encoder = new TextEncoder();
  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>();
  const writer = writable.getWriter();

  // Premier octet immédiat → TTFB bas, Chrome ne suspend pas une connexion « muette ».
  const pump = (async () => {
    try {
      await writer.write(encoder.encode(": connected\n\n"));
      const reader = upstream.body!.getReader();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (value?.byteLength) {
          await writer.write(value);
        }
      }
      await writer.close();
    } catch {
      try {
        await writer.write(
          encoder.encode(
            `event: error\ndata: ${JSON.stringify({ detail: "flux OMR interrompu" })}\n\n`,
          ),
        );
      } catch {
        /* writer déjà fermé */
      }
      try {
        await writer.close();
      } catch {
        /* ignore */
      }
    }
  })();

  // Empêche un rejet non géré si le client coupe avant la fin du pump.
  void pump.catch(() => undefined);

  return new Response(readable, { status: 200, headers: SSE_HEADERS });
}
