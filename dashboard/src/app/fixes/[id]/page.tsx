import { FixJobDetail } from "@/components/FixJobDetail";

export default async function FixJobPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <FixJobDetail id={id} />;
}
