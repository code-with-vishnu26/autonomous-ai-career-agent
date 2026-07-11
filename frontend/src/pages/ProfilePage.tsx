import { useState } from "react";
import { useForm } from "react-hook-form";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";
import { authApi } from "@/services/authApi";

interface ProfileForm {
  displayName: string;
}

export function ProfilePage() {
  const { user } = useAuth();
  const [saved, setSaved] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<ProfileForm>({ defaultValues: { displayName: user?.display_name ?? "" } });

  const onSubmit = handleSubmit(async (values) => {
    setSaved(false);
    await authApi.updateProfile(values.displayName || null);
    setSaved(true);
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Profile</h1>

      <Card className="max-w-md">
        <CardHeader>
          <CardTitle>Account details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="block space-y-1 text-sm">
            <span className="text-muted-foreground">Email</span>
            <Input value={user?.email ?? ""} disabled />
          </label>
          <form onSubmit={onSubmit} className="space-y-4">
            <label className="block space-y-1 text-sm">
              <span className="text-muted-foreground">Display name</span>
              <Input {...register("displayName")} />
            </label>
            {saved && <p className="text-sm text-success">Saved.</p>}
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Saving..." : "Save changes"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
