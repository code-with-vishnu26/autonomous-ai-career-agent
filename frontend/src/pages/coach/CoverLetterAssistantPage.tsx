import { useState } from "react";
import { Wand2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Callout } from "@/components/ui/callout";
import { useCoverLetterTransform } from "@/hooks/useCoach";
import type { CoverLetterMode } from "@/types/api";

const MODE_LABELS: Record<CoverLetterMode, string> = {
  rewrite: "Rewrite",
  shorten: "Shorten",
  more_formal: "More formal",
  more_technical: "More technical",
};

export function CoverLetterAssistantPage() {
  const [body, setBody] = useState("");
  const [mode, setMode] = useState<CoverLetterMode>("rewrite");
  const { mutate, data, isPending, error } = useCoverLetterTransform();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Cover Letter Assistant</h1>
      <Callout>
        The rewrite is verified against your original letter before being
        shown -- if it can&apos;t be confirmed as entailed by your own text
        (no new claim added), it is rejected rather than silently shown.
      </Callout>
      <Card>
        <CardHeader>
          <CardTitle>Paste your cover letter</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              mutate({ body, mode });
            }}
            className="space-y-4"
          >
            <Textarea
              value={body}
              onChange={(event) => setBody(event.target.value)}
              placeholder="Paste your cover letter text here..."
              required
            />
            <label className="block max-w-xs space-y-1 text-sm">
              <span className="text-muted-foreground">Transformation</span>
              <Select
                value={mode}
                onChange={(event) => setMode(event.target.value as CoverLetterMode)}
              >
                {Object.entries(MODE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </label>
            <Button type="submit" disabled={isPending}>
              <Wand2 className="h-4 w-4" />
              {isPending ? "Working..." : "Transform"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {error && <Callout>{(error as Error).message}</Callout>}

      {data && (
        <Card>
          <CardHeader>
            <CardTitle>Result</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Badge variant="muted">Verified {(data.confidence * 100).toFixed(0)}%</Badge>
            <p className="whitespace-pre-wrap text-sm">{data.transformed}</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
