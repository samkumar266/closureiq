"""Run a minimal live Strands agent smoke test."""

from .agent import build_agent


def main() -> None:
    """Build the agent and submit the required explanation prompt."""
    agent = build_agent()
    result = agent("Why is the posture what it is?")
    print(str(result))


if __name__ == "__main__":
    main()
