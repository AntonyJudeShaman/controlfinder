import { Suspense } from "react";
import { Trace } from "@/screens/Trace";

export default function TracePage() {
  return (
    <Suspense>
      <Trace />
    </Suspense>
  );
}
