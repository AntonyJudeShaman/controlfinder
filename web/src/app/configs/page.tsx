import { Suspense } from "react";
import { Configs } from "@/screens/Configs";

export default function ConfigsPage() {
  return (
    <Suspense>
      <Configs />
    </Suspense>
  );
}
