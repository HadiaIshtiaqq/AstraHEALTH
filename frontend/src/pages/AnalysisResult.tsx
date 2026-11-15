import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { TriangleAlert } from "lucide-react";
import { api } from "../api/client";
import type { AnalysisRun } from "../api/types";
import { RunSummary } from "../components/analysis";
import { ErrorBox, PageHeader, Skeleton } from "../components/ui";
import { fmtTime } from "../lib/format";

export default function AnalysisResult() {
  const { runId = "" } = useParams();
  const [params] = useSearchParams();
  const [run, setRun] = useState<AnalysisRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.run(runId).then(setRun).catch((e) => setError(e.message)); }, [runId]);
  if (error) return <ErrorBox message={error} />;
  if (!run) return <Skeleton className="h-96" />;
  return (
    <div>
      <PageHeader title="Analysis result" subtitle={`Completed ${fmtTime(run.completed_at)} · rules ${run.ruleset_version}`} />
      {run.assessment.monitoring_state === "URGENT" && (
        <div role="alert" className="mb-5 flex items-center gap-3 rounded-2xl bg-urgent p-4 text-white">
          <TriangleAlert size={26} aria-hidden /> <b>Urgent: contact the onboard medical officer now.</b> This cannot be downgraded by AI-generated text.
        </div>
      )}
      <RunSummary run={run} animate={params.get("animate") === "1"} />
    </div>
  );
}
