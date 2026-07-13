import { useMemo, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { StatusBadge } from "@/components/StatusBadge";
import { QueryState } from "@/components/QueryState";
import { DownloadExcelButton } from "@/components/DownloadExcelButton";
import { exportApi } from "@/services/exportApi";
import { useApplications } from "@/hooks/useApi";

const PAGE_SIZE = 10;

export function ApplicationsPage() {
  const { data, isLoading, isError } = useApplications();
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rows = data ?? [];
    if (!q) return rows;
    return rows.filter(
      (row) =>
        row.company.toLowerCase().includes(q) || row.job_title.toLowerCase().includes(q),
    );
  }, [data, query]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageRows = filtered.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold">Applications</h1>
        <DownloadExcelButton onDownload={exportApi.applications} />
      </div>

      <Input
        placeholder="Search by company or role..."
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setPage(0);
        }}
        className="max-w-sm"
      />

      <QueryState
        isLoading={isLoading}
        isError={isError}
        isEmpty={filtered.length === 0}
        emptyMessage="No prepared applications yet. Run career-agent prepare to create one."
      >
        <Card>
          <CardContent className="p-0">
            <Table>
              <THead>
                <TR>
                  <TH>Company</TH>
                  <TH>Role</TH>
                  <TH>Status</TH>
                  <TH>Provider</TH>
                  <TH>Resume Variant</TH>
                  <TH>Date</TH>
                </TR>
              </THead>
              <TBody>
                {pageRows.map((row) => (
                  <TR key={row.id}>
                    <TD>{row.company}</TD>
                    <TD>{row.job_title}</TD>
                    <TD>
                      <StatusBadge status={row.status} />
                    </TD>
                    <TD className="capitalize">{row.provider}</TD>
                    <TD>{row.resume_variant_id ?? "—"}</TD>
                    <TD>{new Date(row.created_at).toLocaleDateString()}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </CardContent>
        </Card>

        <div className="flex items-center justify-between pt-4 text-sm text-muted-foreground">
          <span>
            Page {page + 1} of {pageCount} ({filtered.length} applications)
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= pageCount - 1}
              onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            >
              Next
            </Button>
          </div>
        </div>
      </QueryState>
    </div>
  );
}
