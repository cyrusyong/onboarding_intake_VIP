"""
VIP Military Spouse intake CLI.

Run:
    python3 llm.py
"""

import json
import sys

from onboarding_service import (
    FIELD_SCHEMA,
    OllamaError,
    check_ollama,
    describe_missing_fields,
    extract_fields,
    merge_and_finalize,
    save_output,
)


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    RED = "\033[91m"
    DIM = "\033[2m"


def display_extracted(extracted: dict):
    filled = {key: value for key, value in extracted.items() if value not in (None, "", "null")}
    if not filled:
        return

    print(f"\n{C.BOLD}{C.GREEN}You shared:{C.RESET}")
    for key, value in filled.items():
        label = FIELD_SCHEMA[key]["label"]
        val_display = str(value)
        if len(val_display) > 80:
            val_display = f"{val_display[:77]}..."
        print(f"  {label}: {val_display}")


def collect_answers(missing_fields: list[dict]) -> dict:
    if not missing_fields:
        print(f"\n{C.GREEN}We have everything we need. No follow-up questions.{C.RESET}")
        return {}

    print(f"{C.DIM}Press Enter to skip any question.{C.RESET}\n")
    answers = {}
    for field in missing_fields:
        print(f"{C.CYAN}{field['question']}{C.RESET}")
        try:
            answer = input("→ ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{C.DIM}Skipping remaining questions.{C.RESET}")
            break
        if answer:
            answers[field["key"]] = answer
    return answers


def main():
    try:
        check_ollama()
    except OllamaError as exc:
        print(f"{C.RED}{exc}{C.RESET}")
        sys.exit(1)

    print(f"{C.BOLD}Share your story:{C.RESET}")

    lines = []
    try:
        while True:
            line = input()
            if line == "" and lines and lines[-1] == "":
                break
            lines.append(line)
    except (KeyboardInterrupt, EOFError):
        pass

    user_text = "\n".join(lines).strip()
    if not user_text:
        print(f"{C.RED}No input provided. Exiting.{C.RESET}")
        sys.exit(0)

    try:
        extracted = extract_fields(user_text)
        missing_fields = describe_missing_fields(user_text, extracted)
    except OllamaError as exc:
        print(f"{C.RED}{exc}{C.RESET}")
        sys.exit(1)

    display_extracted(extracted)
    answers = collect_answers(missing_fields)
    final = merge_and_finalize(extracted, answers)
    output_path = save_output(final)

    print("\nOUTPUT -> Gap Analysis Agent")
    print(json.dumps(final, indent=2))
    print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
