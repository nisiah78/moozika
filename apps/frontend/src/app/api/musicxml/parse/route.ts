import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const OMR_SERVICE_URL = process.env.OMR_SERVICE_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  const incoming = await req.formData();
  const file = incoming.get("file");
  if (!(file instanceof File)) {
    return NextResponse.json({ detail: "fichier MusicXML manquant" }, { status: 400 });
  }

  const out = new FormData();
  out.append("file", file, file.name);

  try {
    const res = await fetch(`${OMR_SERVICE_URL}/musicxml/parse`, { method: "POST", body: out });
    const data = await res.json().catch(() => ({ detail: "réponse invalide du service" }));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { detail: `service OMR injoignable (${OMR_SERVICE_URL})` },
      { status: 502 },
    );
  }
}
