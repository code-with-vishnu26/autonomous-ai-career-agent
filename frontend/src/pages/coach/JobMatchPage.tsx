import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { ResumeJdForm } from "@/components/coach/ResumeJdForm";
import { useJobMatch } from "@/hooks/useCoach";

export function JobMatchPage() {
  const { mutate, data, isPending, error } = useJobMatch();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Job Match Score</h1>
      <Callout>
        A deterministic keyword-coverage score against this job description --
        not a prediction of your odds, a measure of how much of its
        vocabulary your resume text already covers.
      </Callout>
      <Card>
        <CardHeader>
          <CardTitle>Paste your resume and the job description</CardTitle>
        </CardHeader>
        <CardContent>
          <ResumeJdForm
            isPending={isPending}
            submitLabel="Score match"
            onSubmit={(resumeText, jdText) => mutate({ resumeText, jdText })}
          />
        </CardContent>
      </Card>

      {error && <Callout>{(error as Error).message}</Callout>}

      {data && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Match Score: {data.match_score.toFixed(0)} / 100</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Missing keywords</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {data.missing_keywords.map((item) => (
                <Badge key={item.keyword} variant="outline">
                  {item.keyword} ({item.kind})
                </Badge>
              ))}
              {data.missing_keywords.length === 0 && (
                <span className="text-sm text-muted-foreground">None missing.</span>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
