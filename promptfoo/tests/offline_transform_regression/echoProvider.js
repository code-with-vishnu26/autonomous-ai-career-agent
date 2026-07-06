// Offline mock provider for the transform-placement regression (ADR-0043).
// Returns a canned "Thinking: ...\n{json}" response shaped exactly like the
// real live openai/gpt-oss-120b output recorded during validation -- no
// network call, no API key, nothing paid or free-tier involved.
const CANNED = {
  AWS: {
    verified: false,
    confidence: 0.99,
    category: "skill_not_found",
    detail: "AWS is not in evidence",
  },
  "Improved system performance": {
    verified: true,
    confidence: 0.95,
    category: null,
    detail: "supported",
  },
  // ADR-0044 compound-claim regression: "Led a team of 8 engineers" has
  // two independently unsupported dimensions (metric "8", action "Led").
  // These two fake statement keys stand in for a model picking either
  // valid category, proving tests.yaml's #7 assertion accepts both.
  "Led a team of 8 engineers (metric variant)": {
    verified: false,
    confidence: 0.99,
    category: "metric_unsupported",
    detail: "team size of 8 not supported by any profile evidence",
  },
  "Led a team of 8 engineers (action variant)": {
    verified: false,
    confidence: 0.99,
    category: "unsupported_action_inference",
    detail: "the evidence does not mention leading a team",
  },
};

class EchoProvider {
  id() {
    return "echo-mock-provider";
  }

  async callApi(prompt, context) {
    const statement = context.vars.statement;
    const verdict = CANNED[statement] || {
      verified: false,
      confidence: 0.5,
      category: "evidence_missing",
      detail: "n/a",
    };
    return {
      output:
        'Thinking: We need to check claim: "' +
        statement +
        '". Reasoning about evidence at length...\n' +
        JSON.stringify(verdict),
    };
  }
}

module.exports = EchoProvider;
