import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { ResumeJdForm } from "@/components/coach/ResumeJdForm";
import { useResumeAnalysis } from "@/hooks/useCoach";

export function ResumeAnalysisPage() {
  const { mutate, data, isPending, error } = useResumeAnalysis();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Resume Analysis</h1>
      <Callout>
        A deterministic scan -- no AI judgment call, no fabrication risk.
        The ATS score, missing keywords, weak-bullet flags, and formatting
        checks are all fixed, explainable rules over your own text.
      </Callout>
      <Card>
        <CardHeader>
          <CardTitle>Paste your resume and the job description</CardTitle>
        </CardHeader>
        <CardContent>
          <ResumeJdForm
            isPending={isPending}
            submitLabel="Analyze"
            onSubmit={(resumeText, jdText) => mutate({ resumeText, jdText })}
          />
        </CardContent>
      </Card>

      {error && <Callout>{(error as Error).message}</Callout>}

      {data && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>ATS Score: {data.ats_score.toFixed(0)} / 100</CardTitle>
            </CardHeader>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Matched keywords</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {data.matched_keywords.map((item) => (
                <Badge key={item.keyword}>{item.keyword}</Badge>
              ))}
              {data.matched_keywords.length === 0 && (
                <span className="text-sm text-muted-foreground">None matched.</span>
              )}
            </CardContent>
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

          <Card>
            <CardHeader>
              <CardTitle>Weak bullet points</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {data.weak_bullets.map((issue, index) => (
                <div key={index} className="rounded-md border border-border p-3 text-sm">
                  <p className="font-medium">{issue.text}</p>
                  <p className="text-muted-foreground">{issue.reason}</p>
                </div>
              ))}
              {data.weak_bullets.length === 0 && (
                <span className="text-sm text-muted-foreground">
                  No weak bullets found.
                </span>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Formatting issues</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {data.formatting_issues.map((issue, index) => (
                <p key={index} className="text-sm text-muted-foreground">
                  {issue.reason}
                </p>
              ))}
              {data.formatting_issues.length === 0 && (
                <span className="text-sm text-muted-foreground">None found.</span>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
