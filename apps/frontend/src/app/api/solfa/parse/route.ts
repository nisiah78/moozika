import { NextRequest, NextResponse } from "next/server";

const OMR = (process.env.OMR_SERVICE_URL || "http://localhost:8000").replace(/\/$/, "");

export async function POST(req: NextRequest) {
  const body = await req.text();
  const upstream = await fetch(`${OMR}/solfa/parse`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body,
  });
  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
