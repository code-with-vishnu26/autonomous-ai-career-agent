import { useForm } from "react-hook-form";
import { Search } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Callout } from "@/components/ui/callout";
import { CliOnlyAction } from "@/components/CliOnlyAction";

interface SearchFilters {
  role: string;
  location: string;
  remote: string;
  minSalary: string;
  experience: string;
  provider: string;
}

const DEFAULT_FILTERS: SearchFilters = {
  role: "",
  location: "",
  remote: "any",
  minSalary: "",
  experience: "any",
  provider: "any",
};

export function SearchJobsPage() {
  const { register, handleSubmit } = useForm<SearchFilters>({
    defaultValues: DEFAULT_FILTERS,
  });

  const onSubmit = handleSubmit(() => {
    // No-op: discovery has no API endpoint (Phase 54 is read-only). The
    // form is kept fully interactive so the filter shape is real and
    // ready for a future write-capable phase, but submitting it cannot
    // call anything -- see the CliOnlyAction button below instead.
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Search Jobs</h1>

      <Callout>
        Discovery has no API endpoint yet -- <code>career-agent discover</code> is a
        multi-source, LLM-assisted search run from the CLI. This form previews the
        filter shape (Job Search Preferences, ADR-0064); wiring a real
        &quot;search&quot; action here is a follow-up phase's decision, not this one's.
      </Callout>

      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Role</span>
              <Input placeholder="Software Engineer" {...register("role")} />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Location</span>
              <Input placeholder="Remote, London, ..." {...register("location")} />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Remote</span>
              <Select {...register("remote")}>
                <option value="any">Any</option>
                <option value="remote">Remote only</option>
                <option value="hybrid">Hybrid</option>
                <option value="onsite">On-site</option>
              </Select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Minimum salary</span>
              <Input type="number" placeholder="80000" {...register("minSalary")} />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Experience</span>
              <Select {...register("experience")}>
                <option value="any">Any</option>
                <option value="entry">Entry</option>
                <option value="mid">Mid</option>
                <option value="senior">Senior</option>
              </Select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Provider</span>
              <Select {...register("provider")}>
                <option value="any">Any</option>
                <option value="greenhouse">Greenhouse</option>
                <option value="lever">Lever</option>
                <option value="ashby">Ashby</option>
              </Select>
            </label>
            <div className="sm:col-span-2 lg:col-span-3">
              <CliOnlyAction command="career-agent discover --profile profile.json">
                <Search className="h-4 w-4" />
                Search
              </CliOnlyAction>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
