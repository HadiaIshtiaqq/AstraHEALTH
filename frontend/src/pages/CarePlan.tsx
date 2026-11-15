import { CarePlanPanel } from "../components/CarePlan";
import { PageHeader } from "../components/ui";

export default function CarePlan() {
  return (
    <div className="max-w-4xl">
      <PageHeader title="Your care plan"
        subtitle="What you can do to improve each condition detected in your latest analysis. These are routine countermeasures and self-monitoring steps from the mission library, with goals set against your own usual range — not treatment. The medical officer decides anything clinical." />
      <CarePlanPanel />
    </div>
  );
}
