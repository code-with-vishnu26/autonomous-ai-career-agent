import { Terminal } from "lucide-react";
import { Button, type ButtonProps } from "@/components/ui/button";

/**
 * A button that names the real CLI command instead of faking an API call
 * that doesn't exist. Discover/Review/Submit moved to the dashboard in
 * Phase 63 (ADR-0081) -- this component's remaining job is
 * `career-agent prepare` (tailoring a résumé/cover letter inside a real
 * browser), which stays CLI-only: it has its own real headed-browser
 * complexity deserving its own future audit, not folded into Phase 63.
 * This component is how the dashboard surfaces that boundary honestly
 * instead of shipping a button that does nothing, or a button that lies
 * about what it did.
 */
export function CliOnlyAction({
  command,
  children,
  ...props
}: ButtonProps & { command: string }) {
  return (
    <Button
      variant="outline"
      disabled
      title={`Not available from the dashboard yet -- run: ${command}`}
      {...props}
    >
      <Terminal className="h-4 w-4" />
      {children}
    </Button>
  );
}
