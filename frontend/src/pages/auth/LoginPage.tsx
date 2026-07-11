import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";
import { AuthLayout } from "./AuthLayout";

interface LoginForm {
  email: string;
  password: string;
}

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<LoginForm>();

  const onSubmit = handleSubmit(async (values) => {
    setError(null);
    try {
      await login(values.email, values.password);
      const from = (location.state as { from?: Location })?.from;
      navigate(from ? `${from.pathname}${from.search}` : "/", { replace: true });
    } catch {
      setError("Invalid email or password.");
    }
  });

  return (
    <AuthLayout title="Log in">
      <form onSubmit={onSubmit} className="space-y-4">
        <label className="block space-y-1 text-sm">
          <span className="text-muted-foreground">Email</span>
          <Input type="email" required {...register("email", { required: true })} />
        </label>
        <label className="block space-y-1 text-sm">
          <span className="text-muted-foreground">Password</span>
          <Input
            type="password"
            required
            {...register("password", { required: true })}
          />
        </label>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button type="submit" disabled={isSubmitting} className="w-full">
          {isSubmitting ? "Logging in..." : "Log in"}
        </Button>
      </form>
      <div className="flex justify-between text-sm text-muted-foreground">
        <Link to="/forgot-password" className="hover:text-foreground">
          Forgot password?
        </Link>
        <Link to="/register" className="hover:text-foreground">
          Create an account
        </Link>
      </div>
    </AuthLayout>
  );
}
