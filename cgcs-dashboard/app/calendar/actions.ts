"use server";

import { revalidatePath } from "next/cache";
import { syncCalendar } from "@/lib/api";

export async function syncCalendarAction(_formData: FormData): Promise<void> {
  try {
    const result = await syncCalendar();
    console.log("Calendar sync result:", result);
  } catch (e) {
    console.error("Calendar sync failed:", e);
  }
  revalidatePath("/calendar");
  revalidatePath("/reservations");
  revalidatePath("/");
}
