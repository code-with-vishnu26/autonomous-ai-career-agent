import { useParams } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { QueryState } from "@/components/QueryState";
import { useCheckout, usePlans, useSubscription, useUsage } from "@/hooks/useBilling";
import type { Plan, PlanId } from "@/types/api";

function formatPrice(cents: number): string {
  if (cents === 0) return "Free";
  return `$${(cents / 100).toFixed(0)}/mo`;
}

export function BillingPage() {
  const { organizationId = "" } = useParams<{ organizationId: string }>();
  const plans = usePlans();
  const subscription = useSubscription(organizationId);
  const usage = useUsage(organizationId);
  const checkout = useCheckout(organizationId);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Billing</h1>

      <Callout>
        No real payment processor is connected -- plan changes activate
        immediately, at no charge, using a stub billing provider. See
        ADR-0078 for the production-ready shape this stub is built to.
      </Callout>

      <QueryState
        isLoading={subscription.isLoading || plans.isLoading}
        isError={subscription.isError || plans.isError}
      >
        {subscription.data && (
          <Card className="max-w-md">
            <CardHeader>
              <CardTitle>Current plan</CardTitle>
            </CardHeader>
            <CardContent className="flex items-center justify-between text-sm">
              <span className="capitalize">{subscription.data.plan_id}</span>
              <Badge variant={subscription.data.status === "ACTIVE" ? "success" : "muted"}>
                {subscription.data.status}
              </Badge>
            </CardContent>
          </Card>
        )}

        <div className="grid gap-4 sm:grid-cols-3">
          {plans.data?.map((plan: Plan) => (
            <Card key={plan.id}>
              <CardHeader>
                <CardTitle className="text-base font-semibold text-foreground">
                  {plan.name}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-2xl font-semibold">{formatPrice(plan.monthly_price_cents)}</p>
                <p className="text-xs text-muted-foreground">Up to {plan.max_seats} seats</p>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  {plan.features.map((feature) => (
                    <li key={feature}>&bull; {feature}</li>
                  ))}
                </ul>
                <Button
                  className="w-full"
                  variant={subscription.data?.plan_id === plan.id ? "outline" : "default"}
                  disabled={subscription.data?.plan_id === plan.id || checkout.isPending}
                  onClick={() => checkout.mutate(plan.id as PlanId)}
                >
                  {subscription.data?.plan_id === plan.id ? "Current plan" : "Switch"}
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      </QueryState>

      <Card>
        <CardHeader>
          <CardTitle>Usage</CardTitle>
        </CardHeader>
        <CardContent>
          <QueryState isLoading={usage.isLoading} isError={usage.isError}>
            <div className="space-y-1">
              {usage.data?.map((metric) => (
                <div
                  key={metric.metric}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="capitalize text-muted-foreground">{metric.metric}</span>
                  <span>{metric.count}</span>
                </div>
              ))}
            </div>
          </QueryState>
        </CardContent>
      </Card>
    </div>
  );
}
