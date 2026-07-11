import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";
import { AuthLayout } from "./AuthLayout";

interface RegisterForm {
  email: string;
  password: string;
  displayName: string;
}

export function RegisterPage() {
  const { register: registerAccount } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<RegisterForm>();

  const onSubmit = handleSubmit(async (values) => {
    setError(null);
    try {
      await registerAccount(values.email, values.password, values.displayName || undefined);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create an account.");
    }
  });

  return (
    <AuthLayout title="Create an account">
      <form onSubmit={onSubmit} className="space-y-4">
        <label className="block space-y-1 text-sm">
          <span className="text-muted-foreground">Name (optional)</span>
          <Input {...register("displayName")} />
        </label>
        <label className="block space-y-1 text-sm">
          <span className="text-muted-foreground">Email</span>
          <Input type="email" required {...register("email", { required: true })} />
        </label>
        <label className="block space-y-1 text-sm">
          <span className="text-muted-foreground">Password</span>
          <Input
            type="password"
            required
            minLength={8}
            {...register("password", { required: true, minLength: 8 })}
          />
        </label>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button type="submit" disabled={isSubmitting} className="w-full">
          {isSubmitting ? "Creating account..." : "Create account"}
        </Button>
      </form>
      <p className="text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link to="/login" className="text-foreground hover:underline">
          Log in
        </Link>
      </p>
    </AuthLayout>
  );
}
