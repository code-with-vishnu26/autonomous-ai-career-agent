import { useNavigate } from "react-router-dom";
import { ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";

/** Shown full-page when a request comes back 401 and the automatic
 * refresh attempt also fails (Phase 56, ADR-0074) -- e.g. the refresh
 * token expired or was revoked elsewhere. Names what happened instead of
 * leaving the user staring at a page full of failed requests. */
export function SessionExpiredScreen() {
  const { dismissSessionExpired } = useAuth();
  const navigate = useNavigate();

  const handleLoginAgain = () => {
    dismissSessionExpired();
    navigate("/login", { replace: true });
  };

  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-4 p-6 text-center">
      <ShieldAlert className="h-10 w-10 text-warning" />
      <h1 className="text-xl font-semibold">Your session has expired</h1>
      <p className="max-w-sm text-sm text-muted-foreground">
        For your security, you were signed out after a period of inactivity. Sign in
        again to continue.
      </p>
      <Button onClick={handleLoginAgain}>Log in again</Button>
    </div>
  );
}
