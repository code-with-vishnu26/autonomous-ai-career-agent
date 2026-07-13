import { useState } from "react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Textarea } from "@/components/ui/textarea";
import { useProfileMatch } from "@/hooks/useCoach";

/**
 * Phase 66 (ADR-0084). Scores the onboarded Master Profile against a job
 * description with no résumé paste -- the deterministic ATS/keyword
 * scorers (ADR-0075) fed from stored profile data (Phase 64). A 404 means
 * the user hasn't onboarded yet, so we send them there rather than show a
 * misleading empty score.
 */
export function ProfileMatchPage() {
  const [jdText, setJdText] = useState("");
  const { mutate, data, isPending, error } = useProfileMatch();

  const needsOnboarding =
    error instanceof Error && error.message.toLowerCase().includes("onboarding");

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Match My Profile</h1>
      <Callout>
        A deterministic keyword-coverage score of your saved Master Profile
        against a job description -- no résumé paste, no LLM, no cost. It
        measures how much of the role's vocabulary your profile already
        covers, and what keywords are missing.
      </Callout>

      <Card>
        <CardHeader>
          <CardTitle>Paste the job description</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Textarea
            value={jdText}
            onChange={(event) => setJdText(event.target.value)}
            rows={8}
            placeholder="Paste the full job description here..."
            aria-label="Job description"
          />
          <Button
            onClick={() => mutate({ jdText })}
            disabled={isPending || jdText.trim().length === 0}
          >
            {isPending ? "Scoring…" : "Score my profile"}
          </Button>
        </CardContent>
      </Card>

      {needsOnboarding && (
        <Callout>
          You haven't built your Master Profile yet.{" "}
          <Link to="/onboarding" className="underline">
            Complete onboarding
          </Link>{" "}
          first, then come back to score it.
        </Callout>
      )}
      {error && !needsOnboarding && <Callout>{(error as Error).message}</Callout>}

      {data && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>
                Match Score: {data.match.match_score.toFixed(0)} / 100
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              You qualify for {data.skill_gap.qualifies_percent.toFixed(0)}% of the
              role's required skills.
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Missing keywords</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {data.match.missing_keywords.map((item) => (
                <Badge key={item.keyword} variant="outline">
                  {item.keyword} ({item.kind})
                </Badge>
              ))}
              {data.match.missing_keywords.length === 0 && (
                <span className="text-sm text-muted-foreground">None missing.</span>
              )}
            </CardContent>
          </Card>

          {data.skill_gap.missing_skills.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Skills to add (highest priority first)</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {data.skill_gap.missing_skills.map((gap) => (
                  <div key={gap.keyword} className="text-sm">
                    <span className="font-medium">{gap.keyword}</span>{" "}
                    <span className="text-muted-foreground">
                      ({gap.kind}) — {gap.reason}
                    </span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
