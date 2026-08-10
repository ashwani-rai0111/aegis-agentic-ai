import { IncidentDetailView } from "@/components/IncidentDetailView";

export default async function IncidentPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <IncidentDetailView incidentId={id} />;
}