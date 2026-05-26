"use server";

import { revalidatePath } from "next/cache";
import { updateReservationCategory } from "@/lib/api";

export async function updateCategoryAction(
  id: string,
  category: "cgcs" | "acc" | "monetization",
): Promise<void> {
  try {
    await updateReservationCategory(id, category);
  } catch (e) {
    console.error("updateCategoryAction failed:", e);
    throw e;
  }
  revalidatePath("/reservations");
  revalidatePath("/");
}
