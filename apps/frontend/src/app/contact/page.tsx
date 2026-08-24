import type { Metadata } from "next";
import { ContactScreen } from "@/components/ContactScreen";

export const metadata: Metadata = { title: "Me contacter — moozika" };

export default function ContactPage() {
  return <ContactScreen />;
}
