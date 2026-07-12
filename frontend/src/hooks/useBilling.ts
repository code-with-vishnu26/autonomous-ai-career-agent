/** TanStack Query wrappers over `billingApi` (Phase 60, ADR-0078). */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { billingApi } from "@/services/billingApi";
import type { PlanId } from "@/types/api";

export function usePlans() {
  return useQuery({ queryKey: ["billing", "plans"], queryFn: billingApi.listPlans });
}

export function useSubscription(organizationId: string) {
  return useQuery({
    queryKey: ["billing", organizationId, "subscription"],
    queryFn: () => billingApi.getSubscription(organizationId),
  });
}

export function useUsage(organizationId: string) {
  return useQuery({
    queryKey: ["billing", organizationId, "usage"],
    queryFn: () => billingApi.getUsage(organizationId),
  });
}

export function useCheckout(organizationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (planId: PlanId) => billingApi.checkout(organizationId, planId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["billing", organizationId] });
    },
  });
}
