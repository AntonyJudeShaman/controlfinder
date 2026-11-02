import { Suspense } from "react";
import { Results } from "@/screens/Results";

export default function ResultsPage() {
  return (
    <Suspense>
      <Results />
    </Suspense>
  );
}
