import { redirect } from "next/navigation";
import { ROUTES } from "@/lib/navigation";

export default function LearnRoot() {
  redirect(ROUTES.learn());
}
