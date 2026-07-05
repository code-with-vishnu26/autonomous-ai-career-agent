"""Curated skills taxonomy for deterministic ATS keyword extraction (ADR-0034).

Pure data, deliberately code-reviewed rather than model-derived: the Phase
10 pre-brief found spaCy's statistical model both uninstallable in this
sandbox (proxy-blocked) and -- more importantly -- wrong for a hard gate,
because a score whose keyword extraction depends on a downloaded model
artifact is only deterministic *conditional on* a specific model version
being present. Same input, same code version, same output, forever, on any
machine: that property comes from this list plus pure-Python matching, and
from nothing that ships outside this repository.

Extending this list is an ordinary code change (reviewed, versioned,
visible in a diff) -- exactly how a gate's vocabulary should evolve.

``HARD_SKILLS`` weigh 2x in keyword coverage; ``SOFT_SKILLS`` weigh 1x
(ADR-0034). Matching is case-insensitive with hyphen/space and trailing-s
normalization, handled by :mod:`career_agent.domain.ats_scoring`, so
entries here are written in their canonical display form.
"""

from __future__ import annotations

HARD_SKILLS: frozenset[str] = frozenset(
    {
        # Languages
        "Python", "Java", "JavaScript", "TypeScript", "Go", "Rust", "C++",
        "C#", "Ruby", "PHP", "Swift", "Kotlin", "Scala", "SQL", "R",
        # Frameworks / libraries
        "Django", "Flask", "FastAPI", "React", "Angular", "Vue", "Node.js",
        "Spring", "Rails", ".NET", "Express", "Next.js", "GraphQL",
        "REST API", "gRPC", "Pandas", "NumPy", "PyTorch",
        "TensorFlow", "scikit-learn", "Spark", "Kafka", "Airflow",
        # Infrastructure / platforms
        "Kubernetes", "Docker", "Terraform", "Ansible", "AWS", "Azure",
        "GCP", "Linux", "Git", "CI/CD", "Jenkins", "GitHub Actions",
        "Serverless", "Lambda", "Microservices",
        # Data stores
        "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch",
        "DynamoDB", "SQLite", "Cassandra", "Snowflake", "BigQuery",
        # Practices with hard, checkable meaning
        "Machine Learning", "Deep Learning", "NLP", "Computer Vision",
        "Data Engineering", "ETL", "Distributed Systems", "Observability",
        "Prometheus", "Grafana", "OAuth", "TDD", "Playwright", "Selenium",
    }
)

SOFT_SKILLS: frozenset[str] = frozenset(
    {
        "Leadership", "Mentoring", "Communication", "Collaboration",
        "Stakeholder Management", "Project Management", "Agile", "Scrum",
        "Problem Solving", "Cross-functional", "Ownership",
        "Documentation", "Code Review", "Team Player",
    }
)
