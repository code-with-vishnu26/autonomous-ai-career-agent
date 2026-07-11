import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { authApi } from "@/services/authApi";
import { AuthLayout } from "./AuthLayout";

interface ResetPasswordForm {
  newPassword: string;
}

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<ResetPasswordForm>();

  const onSubmit = handleSubmit(async (values) => {
    setError(null);
    try {
      await authApi.resetPassword(token, values.newPassword);
      navigate("/login", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reset the password.");
    }
  });

  return (
    <AuthLayout title="Reset password">
      {!token ? (
        <Callout>
          This link is missing its reset token. Use the link from the reset email (or
          the one provided directly, since email delivery isn&apos;t wired up yet).
        </Callout>
      ) : (
        <form onSubmit={onSubmit} className="space-y-4">
          <label className="block space-y-1 text-sm">
            <span className="text-muted-foreground">New password</span>
            <Input
              type="password"
              required
              minLength={8}
              {...register("newPassword", { required: true, minLength: 8 })}
            />
          </label>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" disabled={isSubmitting} className="w-full">
            {isSubmitting ? "Resetting..." : "Reset password"}
          </Button>
        </form>
      )}
      <p className="text-sm text-muted-foreground">
        <Link to="/login" className="text-foreground hover:underline">
          Back to log in
        </Link>
      </p>
    </AuthLayout>
  );
}
