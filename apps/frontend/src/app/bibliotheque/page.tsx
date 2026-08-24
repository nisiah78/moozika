import { redirect } from "next/navigation";
import { ROUTES } from "@/lib/navigation";

export default function LibraryRoot() {
  redirect(ROUTES.library());
}
