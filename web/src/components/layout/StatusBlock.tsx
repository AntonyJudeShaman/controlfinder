import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import type { StatusBlockProps } from "@/types/components/layout/status-block";

export function StatusBlock({ status, message }: StatusBlockProps) {
  if (status === "loading") return <Skeleton className="h-40 w-full" />;
  return (
    <Alert variant="destructive">
      <AlertTitle>Could not load</AlertTitle>
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  );
}
