import { useState } from "react";
import { Wand2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

/** Shared resume-text + job-description-text input, used by every Career
 * Coach feature that scores or drafts against a resume/JD pair. */
export function ResumeJdForm({
  onSubmit,
  isPending,
  submitLabel = "Analyze",
}: {
  onSubmit: (resumeText: string, jdText: string) => void;
  isPending: boolean;
  submitLabel?: string;
}) {
  const [resumeText, setResumeText] = useState("");
  const [jdText, setJdText] = useState("");

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(resumeText, jdText);
      }}
      className="space-y-4"
    >
      <label className="block space-y-1 text-sm">
        <span className="text-muted-foreground">Resume text</span>
        <Textarea
          value={resumeText}
          onChange={(event) => setResumeText(event.target.value)}
          placeholder="Paste your resume text here..."
          required
        />
      </label>
      <label className="block space-y-1 text-sm">
        <span className="text-muted-foreground">Job description</span>
        <Textarea
          value={jdText}
          onChange={(event) => setJdText(event.target.value)}
          placeholder="Paste the job description here..."
          required
        />
      </label>
      <Button type="submit" disabled={isPending}>
        <Wand2 className="h-4 w-4" />
        {isPending ? "Working..." : submitLabel}
      </Button>
    </form>
  );
}
