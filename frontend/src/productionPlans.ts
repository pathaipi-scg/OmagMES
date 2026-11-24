export type ProductionPlan = {
  plan_key: string;
  duplicate_count: number;
  plan_name: string | null;
  material_code: string | null;
  material_name: string | null;
  planned_start: string | null;
  machine: string | null;
  shift: string | null;
  plan_count: number | string | null;
  identity_kind: string;
  snapshot: Record<string, unknown>;
  product_match?: {
    status: 'MATCHED' | 'PRODUCT NOT FOUND' | 'AMBIGUOUS';
    product_id: number | null;
    product_code: string | null;
    product_name: string | null;
    product_name_thai?: string | null;
  };
};

export type ProductionPlanResponse = {
  source: string;
  filters: { Company: string; Machine: string; Plant: string };
  plans: ProductionPlan[];
  truncated: boolean;
  limit: number;
  warnings: string[];
  assignment_available?: boolean;
};

let inFlightRequest: { key: string; promise: Promise<ProductionPlanResponse> } | null = null;

/** Share only concurrent reads; a later invocation always fetches a fresh snapshot. */
export function loadProductionPlans(productionDate?: string): Promise<ProductionPlanResponse> {
  const key = productionDate ?? '';
  if (inFlightRequest?.key === key) return inFlightRequest.promise;

  const query = productionDate ? `?${new URLSearchParams({ production_date: productionDate })}` : '';
  const request = fetch(`/api/press-lots/plans${query}`)
    .then(async (response) => {
      if (!response.ok) {
        const body = await response.json().catch(() => null) as { detail?: string } | null;
        throw new Error(body?.detail ?? `Production Plan request failed (${response.status})`);
      }
      return response.json() as Promise<ProductionPlanResponse>;
    });

  const inFlight = { key, promise: request };
  inFlightRequest = inFlight;
  void request.then(
    () => { if (inFlightRequest === inFlight) inFlightRequest = null; },
    () => { if (inFlightRequest === inFlight) inFlightRequest = null; },
  );
  return request;
}
