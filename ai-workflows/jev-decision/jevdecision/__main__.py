"""Command line: ask a question set about a state and print the decision as JSON.

    python -m jevdecision --questions examples/support-ticket.json \
        --state "Help! My payouts have been failing for 3 days."

`--dry-run` prints the provider request instead of sending it, so a question
set can be checked without an API key. Exit codes: 0 success, 1 provider or
response error, 2 invalid input.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from .backends import BACKENDS, create_backend
from .core import BACKEND_ENV, DEFAULT_BACKEND, DecisionModel
from .errors import DecisionError, QuestionError
from .questions import check_question_set, questions_from_spec


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="python -m jevdecision", description=__doc__.split("\n")[0])
    parser.add_argument("--questions", required=True, type=Path,
                        help="JSON file in Jev's question map format")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--state", help="state text")
    source.add_argument("--state-file", type=Path,
                        help="state file; a .json file is sent as a JSON object or list of strings")
    parser.add_argument("--backend", choices=sorted(BACKENDS),
                        default=os.environ.get(BACKEND_ENV) or DEFAULT_BACKEND,
                        help=f"provider (default: ${BACKEND_ENV} or {DEFAULT_BACKEND})")
    parser.add_argument("--model", help="model id (default: the backend's)")
    parser.add_argument("--base-url", help="provider or gateway base URL")
    parser.add_argument("--path", help="endpoint path, e.g. /v1/decisions on a gateway")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--dry-run", action="store_true", help="print the request; send nothing")
    return parser.parse_args(argv)


def load_state(args):
    if args.state is not None:
        return args.state
    text = args.state_file.read_text(encoding="utf-8")
    return json.loads(text) if args.state_file.suffix == ".json" else text


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        spec = json.loads(args.questions.read_text(encoding="utf-8"))
        questions = check_question_set(questions_from_spec(spec))
        state = load_state(args)
        backend = create_backend(args.backend, model=args.model, base_url=args.base_url,
                                 path=args.path, timeout=args.timeout)
    except (OSError, json.JSONDecodeError, QuestionError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.dry_run:
        request = {"url": backend.url, "body": backend.build_request(state, questions)}
        print(json.dumps(request, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    try:
        decision = DecisionModel(backend).decide(state, questions)
    except DecisionError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(decision.to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
