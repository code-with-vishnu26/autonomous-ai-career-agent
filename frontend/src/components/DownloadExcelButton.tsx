/**
 * A button that downloads an Excel workbook (Phase 65, ADR-0083).
 *
 * Wraps an `exportApi` call in a tiny local pending/error state so a slow
 * or failed download shows feedback instead of silently doing nothing --
 * the download itself is a browser file save, not a navigation.
 */

import { useState } from "react";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";

interface DownloadExcelButtonProps {
  onDownload: () => Promise<void>;
  label?: string;
}

export function DownloadExcelButton({
  onDownload,
  label = "Download Excel",
}: DownloadExcelButtonProps) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setPending(true);
    setError(null);
    try {
      await onDownload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button
        variant="outline"
        onClick={handleClick}
        disabled={pending}
        aria-busy={pending}
      >
        <Download className="mr-2 h-4 w-4" />
        {pending ? "Preparing…" : label}
      </Button>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
