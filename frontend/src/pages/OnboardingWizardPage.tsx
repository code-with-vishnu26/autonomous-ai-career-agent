import { useEffect, useState } from "react";
import { Controller, useFieldArray, useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, Check, Plus, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Callout } from "@/components/ui/callout";
import { Badge } from "@/components/ui/badge";
import { QueryState } from "@/components/QueryState";
import { ResumeImportPanel } from "@/components/ResumeImportPanel";
import { useMasterProfile, useUpdateMasterProfile } from "@/hooks/useMasterProfile";
import type { MasterProfileUpdate } from "@/types/api";

const STEPS = [
  "welcome",
  "personal",
  "work",
  "education",
  "skills",
  "projects",
  "legal",
  "review",
] as const;
type Step = (typeof STEPS)[number];

const STEP_LABELS: Record<Step, string> = {
  welcome: "Welcome",
  personal: "Personal Details",
  work: "Work Experience",
  education: "Education",
  skills: "Skills",
  projects: "Projects",
  legal: "Work Authorization",
  review: "Review & Finish",
};

function newId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}

const EMPTY_VALUES: MasterProfileUpdate = {
  basics: {
    name: "",
    email: "",
    phone: null,
    summary: null,
    location: null,
    linkedin_url: null,
    github_url: null,
    website_url: null,
    other_links: [],
  },
  work: [],
  education: [],
  skills: [],
  projects: [],
  legal_status: { work_authorized_us: null, requires_sponsorship: null },
};

/** Splits a textarea's lines into a trimmed, non-empty string array. */
function linesToList(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export function OnboardingWizardPage() {
  const profile = useMasterProfile();
  const update = useUpdateMasterProfile();
  const navigate = useNavigate();
  const [stepIndex, setStepIndex] = useState(0);
  const step = STEPS[stepIndex];

  const { register, control, handleSubmit, reset } = useForm<MasterProfileUpdate>({
    defaultValues: EMPTY_VALUES,
  });
  const work = useFieldArray({ control, name: "work" });
  const education = useFieldArray({ control, name: "education" });
  const skills = useFieldArray({ control, name: "skills" });
  const projects = useFieldArray({ control, name: "projects" });

  useEffect(() => {
    if (profile.data) {
      const { version: _version, ...rest } = profile.data;
      reset(rest);
    }
  }, [profile.data, reset]);

  const onSubmit = handleSubmit((values) => {
    update.mutate(values, {
      onSuccess: () => setStepIndex(STEPS.indexOf("review")),
    });
  });

  const isLastStep = stepIndex === STEPS.length - 1;
  const isFirstStep = stepIndex === 0;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Profile Onboarding</h1>
        <p className="text-sm text-muted-foreground">
          Step {stepIndex + 1} of {STEPS.length}: {STEP_LABELS[step]}
        </p>
      </div>

      <Callout>
        This wizard writes directly to your Master Profile (
        <code>PUT /user/master-profile</code>) -- the same JSON-Resume-shaped
        source of truth <code>career-agent prepare</code>/<code>submit</code>{" "}
        already build résumés against. Upload an existing résumé on the
        Welcome step below to pre-fill this automatically, or fill it in by
        hand.
      </Callout>

      <QueryState isLoading={profile.isLoading} isError={profile.isError}>
        <form onSubmit={onSubmit} className="space-y-6">
          {step === "welcome" && (
            <div className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Welcome</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm text-muted-foreground">
                  <p>
                    This short wizard captures what a tailored résumé is built
                    from: your basics, work history, education, skills, and
                    projects.
                  </p>
                  <p>
                    Job Search Preferences (what you're looking for) and
                    Notification Settings are configured separately -- links
                    are on the final step.
                  </p>
                </CardContent>
              </Card>
              <ResumeImportPanel />
            </div>
          )}

          {step === "personal" && (
            <Card>
              <CardHeader>
                <CardTitle>Personal Details</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 sm:grid-cols-2">
                <label className="space-y-1 text-sm">
                  <span className="text-muted-foreground">Full name *</span>
                  <Input {...register("basics.name", { required: true })} />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-muted-foreground">Email *</span>
                  <Input type="email" {...register("basics.email", { required: true })} />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-muted-foreground">Phone</span>
                  <Input {...register("basics.phone")} />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-muted-foreground">Location</span>
                  <Input placeholder="City, Country" {...register("basics.location")} />
                </label>
                <label className="space-y-1 text-sm sm:col-span-2">
                  <span className="text-muted-foreground">Summary</span>
                  <Textarea
                    placeholder="One or two sentences describing who you are professionally."
                    {...register("basics.summary")}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-muted-foreground">LinkedIn</span>
                  <Input
                    placeholder="https://linkedin.com/in/you"
                    {...register("basics.linkedin_url")}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-muted-foreground">GitHub</span>
                  <Input
                    placeholder="https://github.com/you"
                    {...register("basics.github_url")}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-muted-foreground">Portfolio / website</span>
                  <Input
                    placeholder="https://you.dev"
                    {...register("basics.website_url")}
                  />
                </label>
                <Controller
                  control={control}
                  name="basics.other_links"
                  render={({ field: linksField }) => (
                    <label className="space-y-1 text-sm sm:col-span-2">
                      <span className="text-muted-foreground">
                        Other links (one per line)
                      </span>
                      <Textarea
                        defaultValue={(linksField.value ?? []).join("\n")}
                        onChange={(e) => linksField.onChange(linesToList(e.target.value))}
                      />
                    </label>
                  )}
                />
              </CardContent>
            </Card>
          )}

          {step === "work" && (
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>Work Experience</CardTitle>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    work.append({
                      id: newId("work"),
                      name: "",
                      position: "",
                      start_date: "",
                      end_date: null,
                      highlights: [],
                    })
                  }
                >
                  <Plus className="h-4 w-4" />
                  Add role
                </Button>
              </CardHeader>
              <CardContent className="space-y-4">
                {work.fields.length === 0 && (
                  <p className="text-sm text-muted-foreground">No work experience added yet.</p>
                )}
                {work.fields.map((field, index) => (
                  <div key={field.id} className="space-y-3 rounded-md border border-border p-3">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <label className="space-y-1 text-sm">
                        <span className="text-muted-foreground">Company</span>
                        <Input {...register(`work.${index}.name`, { required: true })} />
                      </label>
                      <label className="space-y-1 text-sm">
                        <span className="text-muted-foreground">Position</span>
                        <Input {...register(`work.${index}.position`, { required: true })} />
                      </label>
                      <label className="space-y-1 text-sm">
                        <span className="text-muted-foreground">Start date</span>
                        <Input type="date" {...register(`work.${index}.start_date`, { required: true })} />
                      </label>
                      <label className="space-y-1 text-sm">
                        <span className="text-muted-foreground">
                          End date (blank = current role)
                        </span>
                        <Input type="date" {...register(`work.${index}.end_date`)} />
                      </label>
                    </div>
                    <Controller
                      control={control}
                      name={`work.${index}.highlights`}
                      render={({ field: highlightField }) => (
                        <label className="space-y-1 text-sm">
                          <span className="text-muted-foreground">
                            Highlights (one per line)
                          </span>
                          <Textarea
                            defaultValue={highlightField.value.join("\n")}
                            onChange={(e) => highlightField.onChange(linesToList(e.target.value))}
                          />
                        </label>
                      )}
                    />
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => work.remove(index)}
                    >
                      <Trash2 className="h-4 w-4" />
                      Remove
                    </Button>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {step === "education" && (
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>Education</CardTitle>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    education.append({
                      id: newId("education"),
                      institution: "",
                      area: null,
                      study_type: null,
                      start_date: null,
                      end_date: null,
                    })
                  }
                >
                  <Plus className="h-4 w-4" />
                  Add education
                </Button>
              </CardHeader>
              <CardContent className="space-y-4">
                {education.fields.length === 0 && (
                  <p className="text-sm text-muted-foreground">No education added yet.</p>
                )}
                {education.fields.map((field, index) => (
                  <div key={field.id} className="space-y-3 rounded-md border border-border p-3">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <label className="space-y-1 text-sm">
                        <span className="text-muted-foreground">Institution</span>
                        <Input {...register(`education.${index}.institution`, { required: true })} />
                      </label>
                      <label className="space-y-1 text-sm">
                        <span className="text-muted-foreground">Field of study</span>
                        <Input {...register(`education.${index}.area`)} />
                      </label>
                      <label className="space-y-1 text-sm">
                        <span className="text-muted-foreground">Degree</span>
                        <Input placeholder="BSc, MSc, ..." {...register(`education.${index}.study_type`)} />
                      </label>
                      <label className="space-y-1 text-sm">
                        <span className="text-muted-foreground">Start date</span>
                        <Input type="date" {...register(`education.${index}.start_date`)} />
                      </label>
                      <label className="space-y-1 text-sm">
                        <span className="text-muted-foreground">End date</span>
                        <Input type="date" {...register(`education.${index}.end_date`)} />
                      </label>
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => education.remove(index)}
                    >
                      <Trash2 className="h-4 w-4" />
                      Remove
                    </Button>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {step === "skills" && (
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>Skills</CardTitle>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    skills.append({ id: newId("skill"), name: "", level: null, keywords: [] })
                  }
                >
                  <Plus className="h-4 w-4" />
                  Add skill group
                </Button>
              </CardHeader>
              <CardContent className="space-y-4">
                {skills.fields.length === 0 && (
                  <p className="text-sm text-muted-foreground">No skills added yet.</p>
                )}
                {skills.fields.map((field, index) => (
                  <div key={field.id} className="space-y-3 rounded-md border border-border p-3">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <label className="space-y-1 text-sm">
                        <span className="text-muted-foreground">Group name</span>
                        <Input placeholder="Languages" {...register(`skills.${index}.name`, { required: true })} />
                      </label>
                      <label className="space-y-1 text-sm">
                        <span className="text-muted-foreground">Level</span>
                        <Input placeholder="Advanced" {...register(`skills.${index}.level`)} />
                      </label>
                    </div>
                    <Controller
                      control={control}
                      name={`skills.${index}.keywords`}
                      render={({ field: keywordField }) => (
                        <label className="space-y-1 text-sm">
                          <span className="text-muted-foreground">
                            Keywords (comma-separated)
                          </span>
                          <Input
                            defaultValue={keywordField.value.join(", ")}
                            onChange={(e) =>
                              keywordField.onChange(
                                e.target.value
                                  .split(",")
                                  .map((k) => k.trim())
                                  .filter(Boolean),
                              )
                            }
                          />
                        </label>
                      )}
                    />
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => skills.remove(index)}
                    >
                      <Trash2 className="h-4 w-4" />
                      Remove
                    </Button>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {step === "projects" && (
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>Projects</CardTitle>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    projects.append({
                      id: newId("project"),
                      name: "",
                      description: null,
                      url: null,
                      highlights: [],
                      keywords: [],
                    })
                  }
                >
                  <Plus className="h-4 w-4" />
                  Add project
                </Button>
              </CardHeader>
              <CardContent className="space-y-4">
                {projects.fields.length === 0 && (
                  <p className="text-sm text-muted-foreground">No projects added yet.</p>
                )}
                {projects.fields.map((field, index) => (
                  <div key={field.id} className="space-y-3 rounded-md border border-border p-3">
                    <label className="space-y-1 text-sm">
                      <span className="text-muted-foreground">Name</span>
                      <Input {...register(`projects.${index}.name`, { required: true })} />
                    </label>
                    <label className="space-y-1 text-sm">
                      <span className="text-muted-foreground">Description</span>
                      <Textarea {...register(`projects.${index}.description`)} />
                    </label>
                    <label className="space-y-1 text-sm">
                      <span className="text-muted-foreground">
                        Link (GitHub repo, live demo, ...)
                      </span>
                      <Input
                        placeholder="https://github.com/you/project"
                        {...register(`projects.${index}.url`)}
                      />
                    </label>
                    <Controller
                      control={control}
                      name={`projects.${index}.highlights`}
                      render={({ field: highlightField }) => (
                        <label className="space-y-1 text-sm">
                          <span className="text-muted-foreground">
                            Highlights (one per line)
                          </span>
                          <Textarea
                            defaultValue={highlightField.value.join("\n")}
                            onChange={(e) => highlightField.onChange(linesToList(e.target.value))}
                          />
                        </label>
                      )}
                    />
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => projects.remove(index)}
                    >
                      <Trash2 className="h-4 w-4" />
                      Remove
                    </Button>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {step === "legal" && (
            <Card>
              <CardHeader>
                <CardTitle>Work Authorization</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 sm:grid-cols-2">
                <label className="space-y-1 text-sm">
                  <span className="text-muted-foreground">Authorized to work in the US?</span>
                  <Controller
                    control={control}
                    name="legal_status.work_authorized_us"
                    render={({ field }) => (
                      <Select
                        value={field.value === null ? "skip" : String(field.value)}
                        onChange={(e) =>
                          field.onChange(
                            e.target.value === "skip" ? null : e.target.value === "true",
                          )
                        }
                      >
                        <option value="skip">Never asked / skip</option>
                        <option value="true">Yes</option>
                        <option value="false">No</option>
                      </Select>
                    )}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-muted-foreground">Requires sponsorship?</span>
                  <Controller
                    control={control}
                    name="legal_status.requires_sponsorship"
                    render={({ field }) => (
                      <Select
                        value={field.value === null ? "skip" : String(field.value)}
                        onChange={(e) =>
                          field.onChange(
                            e.target.value === "skip" ? null : e.target.value === "true",
                          )
                        }
                      >
                        <option value="skip">Never asked / skip</option>
                        <option value="true">Yes</option>
                        <option value="false">No</option>
                      </Select>
                    )}
                  />
                </label>
              </CardContent>
            </Card>
          )}

          {step === "review" && (
            <div className="space-y-4">
              {update.isSuccess ? (
                <Callout>
                  <div className="flex items-center gap-2">
                    <Check className="h-4 w-4 text-success" />
                    Profile saved. Next: set your{" "}
                    <button
                      type="button"
                      className="underline"
                      onClick={() => navigate("/search")}
                    >
                      Job Search Preferences
                    </button>{" "}
                    or{" "}
                    <button
                      type="button"
                      className="underline"
                      onClick={() => navigate("/notification-settings")}
                    >
                      Notification Settings
                    </button>
                    .
                  </div>
                </Callout>
              ) : (
                <Callout>Review the summary below, then save.</Callout>
              )}
              {update.isError && (
                <p className="text-sm text-destructive">{(update.error as Error).message}</p>
              )}
              <Card>
                <CardHeader>
                  <CardTitle>Summary</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <p>
                    {work.fields.length} work entr{work.fields.length === 1 ? "y" : "ies"},{" "}
                    {education.fields.length} education entr
                    {education.fields.length === 1 ? "y" : "ies"}, {skills.fields.length} skill
                    group{skills.fields.length === 1 ? "" : "s"}, {projects.fields.length} project
                    {projects.fields.length === 1 ? "" : "s"}.
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {skills.fields.map((field, index) => (
                      <Badge key={field.id} variant="muted">
                        {field.name || `Skill group ${index + 1}`}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          <div className="flex items-center justify-between">
            <Button
              type="button"
              variant="outline"
              disabled={isFirstStep}
              onClick={() => setStepIndex((i) => Math.max(0, i - 1))}
            >
              <ArrowLeft className="h-4 w-4" />
              Back
            </Button>
            {isLastStep ? (
              <Button type="submit" disabled={update.isPending}>
                <Check className="h-4 w-4" />
                {update.isPending ? "Saving..." : "Save profile"}
              </Button>
            ) : (
              <Button
                type="button"
                onClick={() => setStepIndex((i) => Math.min(STEPS.length - 1, i + 1))}
              >
                Next
                <ArrowRight className="h-4 w-4" />
              </Button>
            )}
          </div>
        </form>
      </QueryState>
    </div>
  );
}
