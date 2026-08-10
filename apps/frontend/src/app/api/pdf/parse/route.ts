import { NextRequest, NextResponse } from "next/server";
import { fetch as undiciFetch, Agent } from "undici";

// Route serveur : relaie l'upload vers omr-service (évite CORS et masque
// l'URL interne). Passera par Symfony quand le backend métier existera.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const OMR_SERVICE_URL = process.env.OMR_SERVICE_URL ?? "http://localhost:8000";

// L'OCR (PaddleOCR) d'un fihirana scanné prend plusieurs dizaines de secondes.
// Le `fetch` global de Node applique des timeouts undici (headers/body = 300 s)
// qui coupent la requête en plein OCR → 502. Impossible de les régler sur le
// fetch global : on relaie donc via LE fetch d'undici, avec un dispatcher dont
// les timeouts sont portés à 10 min. Le corps est transmis brut (multipart
// intact), sans re-encoder de FormData.
const dispatcher = new Agent({ headersTimeout: 600_000, bodyTimeout: 600_000 });

export async function POST(req: NextRequest) {
  const contentType = req.headers.get("content-type") ?? "application/octet-stream";
  const body = Buffer.from(await req.arrayBuffer());

  try {
    const res = await undiciFetch(`${OMR_SERVICE_URL}/pdf/parse`, {
      method: "POST",
      headers: { "content-type": contentType },
      body,
      dispatcher,
    });
    const text = await res.text();
    let data: unknown;
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: "réponse invalide du service" };
    }
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { detail: `service OMR injoignable ou trop lent (${OMR_SERVICE_URL})` },
      { status: 502 },
    );
  }
}
