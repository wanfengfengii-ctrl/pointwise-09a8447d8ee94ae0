"""Single demo entry: original briefing scenario plus the cross-revision carry scenario."""

from carry_examples import demo as carry_demo
from tests.fixtures import main as briefing_demo


def main() -> None:
    briefing_demo()
    carry_demo()


if __name__ == '__main__':
    main()
