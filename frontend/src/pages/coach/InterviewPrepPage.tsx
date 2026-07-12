import { useState } from "react";
import { Wand2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Callout } from "@/components/ui/callout";
import { useInterviewPrep } from "@/hooks/useCoach";
import type { PrepQuestion } from "@/types/api";

function QuestionList({ questions }: { questions: PrepQuestion[] }) {
  if (questions.length === 0) {
    return <span className="text-sm text-muted-foreground">None generated.</span>;
  }
  return (
    <div className="space-y-3">
      {questions.map((item, index) => (
        <div key={index} className="rounded-md border border-border p-3 text-sm">
          <p className="font-medium">{item.question}</p>
          <p className="text-muted-foreground">{item.why}</p>
        </div>
      ))}
    </div>
  );
}

export function InterviewPrepPage() {
  const [jdText, setJdText] = useState("");
  const { mutate, data, isPending, error } = useInterviewPrep();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Interview Preparation</h1>
      <Callout>
        Every question is grounded only in this job description -- not
        invented outside knowledge about the company. Company Research
        (the feature that would need real employer data) is a separate,
        deferred page.
      </Callout>
      <Card>
        <CardHeader>
          <CardTitle>Paste the job description</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              mutate({ jdText });
            }}
            className="space-y-4"
          >
            <Textarea
              value={jdText}
              onChange={(event) => setJdText(event.target.value)}
              placeholder="Paste the job description here..."
              required
            />
            <Button type="submit" disabled={isPending}>
              <Wand2 className="h-4 w-4" />
              {isPending ? "Working..." : "Generate prep material"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {error && <Callout>{(error as Error).message}</Callout>}

      {data && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>STAR guidance</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm">{data.star_guidance}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Technical questions</CardTitle>
            </CardHeader>
            <CardContent>
              <QuestionList questions={data.technical_questions} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Behavioral questions</CardTitle>
            </CardHeader>
            <CardContent>
              <QuestionList questions={data.behavioral_questions} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Role-specific questions</CardTitle>
            </CardHeader>
            <CardContent>
              <QuestionList questions={data.role_specific_questions} />
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
