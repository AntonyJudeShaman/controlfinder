import { Suspense } from "react";
import { Controls } from "@/screens/Controls";

export default function ControlsPage() {
  return (
    <Suspense>
      <Controls />
    </Suspense>
  );
}
