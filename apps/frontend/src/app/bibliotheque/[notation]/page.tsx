import { notFound } from "next/navigation";
import { isNotation, NOTATIONS } from "@/lib/navigation";
import { LibraryScreen } from "@/components/LibraryScreen";

/** Les deux notations sont connues : la coquille est prérendue, seule la
    liste des partitions est chargée côté client. */
export function generateStaticParams() {
  return NOTATIONS.map((notation) => ({ notation }));
}

export default function LibraryPage({ params }: { params: { notation: string } }) {
  if (!isNotation(params.notation)) notFound();
  return <LibraryScreen notation={params.notation} />;
}
