
"""Run a minimal live Strands agent smoke test."""

from .agent import build_agent


def main() -> None:
    """Build the agent and submit a concise evaluation explanation."""
    agent = build_agent()

    result = agent(
        "Call get_evaluation with evaluation_id='eval_0012'. "
        "Explain the final posture, the two driving evidence items, "
        "the crossed thresholds, and the decision deadline in no more "
        "than 120 words. Use only the returned evaluation."
    )

    print(str(result))


if __name__ == "__main__":
    main()
