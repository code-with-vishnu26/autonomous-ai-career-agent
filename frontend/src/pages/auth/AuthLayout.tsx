import type { ReactNode } from "react";
import { Briefcase, Moon, Sun } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useThemeContext } from "@/hooks/useThemeContext";

export function AuthLayout({ title, children }: { title: string; children: ReactNode }) {
  const { theme, toggle } = useThemeContext();

  return (
    <div className="relative flex min-h-svh items-center justify-center p-6">
      <Button
        variant="ghost"
        size="icon"
        aria-label="Toggle dark mode"
        onClick={toggle}
        className="absolute right-4 top-4"
      >
        {theme === "dark" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
      </Button>
      <div className="w-full max-w-sm space-y-6">
        <div className="flex items-center justify-center gap-2">
          <Briefcase className="h-6 w-6 text-primary" />
          <span className="font-semibold">Career Agent</span>
        </div>
        <Card>
          <CardContent className="space-y-4 p-6">
            <h1 className="text-lg font-semibold">{title}</h1>
            {children}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
