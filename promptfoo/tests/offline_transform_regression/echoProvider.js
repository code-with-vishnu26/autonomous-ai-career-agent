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
