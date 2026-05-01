"use server";

import { revalidatePath } from "next/cache";
import { approveEmail, rejectEmail } from "@/lib/api";

export async function approveAction(formData: FormData) {
  const id = String(formData.get("id") ?? "");
  if (!id) return;
  await approveEmail(id);
  revalidatePath("/inbox");
}

export async function rejectAction(formData: FormData) {
  const id = String(formData.get("id") ?? "");
  if (!id) return;
  await rejectEmail(id);
  revalidatePath("/inbox");
}
