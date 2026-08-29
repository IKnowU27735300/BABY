---
name: Write Production Unit Tests
description: Generates a comprehensive, production-grade unit test suite covering happy paths, edge cases, error handling, and security.
invokable: true
---

Act as a Staff-level engineer. Analyze the provided code and write a thorough, production-ready unit test suite. 

Do not just write basic happy-path tests. Treat this as code that will run in production with real users and money on the line.

## Testing Requirements

1. **Framework Selection**: Automatically detect and use the idiomatic testing framework for the language/stack (e.g., Jest/Vitest for JS/TS, Pytest for Python, `testing` for Go, JUnit for Java, XCTest for Swift).
2. **Comprehensive Coverage**:
   - **Happy Path**: Verify baseline functionality works as expected.
   - **Edge Cases**: Nulls, undefined, empty collections, boundary values, max limits, unicode, and extreme inputs.
   - **Error Handling**: Verify correct exceptions/errors are thrown, error messages are accurate, and failure modes are handled gracefully.
   - **Security & Safety**: Test for injection vulnerabilities, auth bypasses, and malformed/malicious inputs.
   - **State & Side Effects**: Ensure state is mutated correctly and external side effects (DB writes, API calls, file I/O) are properly mocked and verified.
3. **Best Practices**:
   - Use **Arrange-Act-Assert (AAA)** or **Given-When-Then** structure.
   - Write clear, descriptive test names that explain the scenario and expected outcome (e.g., `should throw ValidationError when email format is invalid`).
   - **Isolate tests**: No test should depend on the state of another. Use proper setup/teardown or fixtures.
   - **Mock external dependencies**: Never hit real databases, networks, or file systems in unit tests. Use mocks/stubs/fakes.
   - **No hallucinations**: Only use real, existing APIs and assertions from the chosen testing framework. Do not invent methods.
4. **Completeness**: Provide the full test file(s), including all necessary imports, mocks, and setup code. Do not leave `// TODO: add more tests` or placeholder logic.

## Output Format

- Briefly state the testing framework chosen and any assumptions made.
- Provide the complete, runnable test code.
- If the original code is untestable as written (e.g., tightly coupled, hidden side effects), briefly explain why and suggest how to refactor it for testability before providing the best-effort tests.



