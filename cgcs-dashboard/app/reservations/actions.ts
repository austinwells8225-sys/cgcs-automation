"use server";

import { revalidatePath } from "next/cache";
import { createReservation, updateReservationCategory, updateReservationFields } from "@/lib/api";

export async function createReservationAction(
  payload: Record<string, unknown>,
): Promise<{ ok: true; id: string } | { ok: false; error: string }> {
  try {
    const created = await createReservation(payload);
    revalidatePath("/reservations");
    revalidatePath("/");
    return { ok: true, id: created.id };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("createReservationAction failed:", msg);
    return { ok: false, error: msg };
  }
}

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

export async function updateFieldsAction(
  id: string,
  updates: Record<string, unknown>,
): Promise<void> {
  try {
    await updateReservationFields(id, updates);
  } catch (e) {
    console.error("updateFieldsAction failed:", e);
    throw e;
  }
  revalidatePath("/reservations");
  revalidatePath("/");
}
