import { Terminal } from "lucide-react";
import { Button, type ButtonProps } from "@/components/ui/button";

/**
 * A button that names the real CLI command instead of faking an API call
 * that doesn't exist. Phase 54 (ADR-0072) deliberately ships no
 * discover/approve/reject/submit endpoint -- those stay exclusively
 * `career-agent discover`/`review`/`submit` actions, most importantly so
 * ADR-0071's fail-closed submission gate (a blocking terminal countdown +
 * ENTER confirmation) is never silently reproduced, or worse
 * mis-reproduced, over HTTP. This component is how every page in this
 * dashboard surfaces that boundary honestly instead of shipping a button
 * that does nothing, or a button that lies about what it did.
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
