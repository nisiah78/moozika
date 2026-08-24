import { notFound } from "next/navigation";
import { isNotation, NOTATIONS } from "@/lib/navigation";
import { LearnScreen } from "@/components/LearnScreen";

export function generateStaticParams() {
  return NOTATIONS.map((notation) => ({ notation }));
}

export default function LearnPage({ params }: { params: { notation: string } }) {
  if (!isNotation(params.notation)) notFound();
  return <LearnScreen notation={params.notation} />;
}
