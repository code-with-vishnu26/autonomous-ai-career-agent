import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { authApi } from "@/services/authApi";
import { AuthLayout } from "./AuthLayout";

interface ForgotPasswordForm {
  email: string;
}

export function ForgotPasswordPage() {
  const [submitted, setSubmitted] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<ForgotPasswordForm>();

  const onSubmit = handleSubmit(async (values) => {
    await authApi.forgotPassword(values.email);
    setSubmitted(true);
  });

  return (
    <AuthLayout title="Forgot password">
      {submitted ? (
        <Callout>
          If that email is registered, a password reset is now possible. Email
          delivery isn&apos;t wired up yet (a future phase) -- ask whoever runs this
          install for the reset link in the meantime.
        </Callout>
      ) : (
        <form onSubmit={onSubmit} className="space-y-4">
          <label className="block space-y-1 text-sm">
            <span className="text-muted-foreground">Email</span>
            <Input type="email" required {...register("email", { required: true })} />
          </label>
          <Button type="submit" disabled={isSubmitting} className="w-full">
            {isSubmitting ? "Sending..." : "Send reset link"}
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
