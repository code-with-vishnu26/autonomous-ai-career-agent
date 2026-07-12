import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Callout } from "@/components/ui/callout";
import { ResumeJdForm } from "@/components/coach/ResumeJdForm";
import { useSkillGap } from "@/hooks/useCoach";

export function SkillGapPage() {
  const { mutate, data, isPending, error } = useSkillGap();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Skill Gap Analysis</h1>
      <Callout>
        &quot;Learning priority&quot; is a fixed, explainable heuristic (hard
        skills first, then by how early each one appears in the job
        description) -- not a learned model. There is no outcome data
        (interviews, offers) in this project to rank skills by real impact;
        see the Weekly Career Report page for why.
      </Callout>
      <Card>
        <CardHeader>
          <CardTitle>Paste your resume and the job description</CardTitle>
        </CardHeader>
        <CardContent>
          <ResumeJdForm
            isPending={isPending}
            submitLabel="Find gaps"
            onSubmit={(resumeText, jdText) => mutate({ resumeText, jdText })}
          />
        </CardContent>
      </Card>

      {error && <Callout>{(error as Error).message}</Callout>}

      {data && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Qualifies: {data.qualifies_percent.toFixed(0)}%</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Missing skills, ranked by priority</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {data.missing_skills.map((gap) => (
                <div key={gap.keyword} className="rounded-md border border-border p-3 text-sm">
                  <p className="font-medium">{gap.keyword}</p>
                  <p className="text-muted-foreground">{gap.reason}</p>
                </div>
              ))}
              {data.missing_skills.length === 0 && (
                <span className="text-sm text-muted-foreground">No gaps found.</span>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
