/**
 * Thin fetch wrapper over `/billing/*` (Phase 60, ADR-0078). No Stripe --
 * see `integrations/billing.py`'s own docstring for why.
 */

import { apiFetchJson } from "./http";
import type { CheckoutResult, Plan, PlanId, Subscription, UsageMetric } from "@/types/api";

export const billingApi = {
  listPlans: () => apiFetchJson<Plan[]>("/billing/plans"),
  getSubscription: (organizationId: string) =>
    apiFetchJson<Subscription>(`/billing/${organizationId}`),
  checkout: (organizationId: string, planId: PlanId) =>
    apiFetchJson<CheckoutResult>(`/billing/${organizationId}/checkout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan_id: planId }),
    }),
  getUsage: (organizationId: string) =>
    apiFetchJson<UsageMetric[]>(`/billing/${organizationId}/usage`),
};
