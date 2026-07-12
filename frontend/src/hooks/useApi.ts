import { useQuery } from "@tanstack/react-query";
import { api } from "@/services/api";
import { reviewsApi } from "@/services/reviewsApi";

export function useApplications() {
  return useQuery({ queryKey: ["applications"], queryFn: api.applications });
}

export function useReviews() {
  return useQuery({ queryKey: ["reviews"], queryFn: reviewsApi.list });
}

export function usePendingReviews() {
  return useQuery({ queryKey: ["reviews", "pending"], queryFn: reviewsApi.pending });
}

export function useSubmissions() {
  return useQuery({ queryKey: ["submissions"], queryFn: api.submissions });
}

export function useResumeVariants() {
  return useQuery({ queryKey: ["resume-variants"], queryFn: api.resumeVariants });
}

export function useAnalyticsSummary() {
  return useQuery({ queryKey: ["analytics", "summary"], queryFn: api.analyticsSummary });
}

export function useSettings() {
  return useQuery({ queryKey: ["settings"], queryFn: api.settings });
}
