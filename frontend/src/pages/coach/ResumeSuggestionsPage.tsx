import { useState } from "react";
import { Check, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { ResumeJdForm } from "@/components/coach/ResumeJdForm";
import { useResumeSuggestions } from "@/hooks/useCoach";
import type { ResumeSuggestion } from "@/types/api";

type Decision = "accepted" | "rejected" | undefined;

function SuggestionCard({ suggestion }: { suggestion: ResumeSuggestion }) {
  const [decision, setDecision] = useState<Decision>();

  return (
    <div className="space-y-2 rounded-md border border-border p-3 text-sm">
      <p className="text-muted-foreground line-through">{suggestion.original}</p>
      <p className="font-medium">{suggestion.suggested}</p>
      <p className="text-muted-foreground">{suggestion.reason}</p>
      <Badge variant="muted">Verified {(suggestion.confidence * 100).toFixed(0)}%</Badge>
      <div className="flex gap-2 pt-1">
        <Button
          type="button"
          size="sm"
          variant={decision === "accepted" ? "default" : "outline"}
          onClick={() => setDecision("accepted")}
        >
          <Check className="h-4 w-4" />
          Accept
        </Button>
        <Button
          type="button"
          size="sm"
          variant={decision === "rejected" ? "destructive" : "outline"}
          onClick={() => setDecision("rejected")}
        >
          <X className="h-4 w-4" />
          Reject
        </Button>
      </div>
      {decision && (
        <p className="text-xs text-muted-foreground">
          {decision === "accepted"
            ? "Marked accepted -- copy this into your resume yourself; nothing is applied automatically."
            : "Marked rejected -- ignored."}
        </p>
      )}
    </div>
  );
}

export function ResumeSuggestionsPage() {
  const { mutate, data, isPending, error } = useResumeSuggestions();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">AI Resume Suggestions</h1>
      <Callout>
        Every suggestion only rewords an existing bullet -- the advisor is
        never asked to invent a new fact, and every rewording is
        independently verified against your original text before being
        shown here. Suggestions are advisory only: nothing is ever applied
        automatically. Accept/Reject below is a local note for you, not a
        write to anything.
      </Callout>
      <Card>
        <CardHeader>
          <CardTitle>Paste your resume and the job description</CardTitle>
        </CardHeader>
        <CardContent>
          <ResumeJdForm
            isPending={isPending}
            submitLabel="Suggest improvements"
            onSubmit={(resumeText, jdText) => mutate({ resumeText, jdText })}
          />
        </CardContent>
      </Card>

      {error && <Callout>{(error as Error).message}</Callout>}

      {data && (
        <Card>
          <CardHeader>
            <CardTitle>Suggestions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.map((suggestion, index) => (
              <SuggestionCard key={index} suggestion={suggestion} />
            ))}
            {data.length === 0 && (
              <span className="text-sm text-muted-foreground">
                No suggestions could be verified against your original text.
              </span>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
