# Intake Reliability Edge-Case Matrix

## Identity and submission mode

- [x] Self-application role is explicit and case-normalized.
- [x] Self-attestation is required in both step and final validation.
- [x] Checked attestation survives draft restoration and is serialized explicitly.
- [x] Switching between agency and self modes resynchronizes steps and controls.
- [x] Shared email addresses cannot silently identify different guests.
- [x] Repeat applications for the same identity preserve application history without inheriting an old decision.

## Required and optional answers

- [x] Every high-signal editorial field is enforced server-side.
- [x] Missing and whitespace-only required values are rejected.
- [x] Website and social profiles are optional in both browser and server validation.
- [x] Concise optional boundaries and speaking context are accepted.
- [x] One-word professions, topics, and listener takeaways remain valid.
- [x] Nested objects and arrays cannot be stringified into text fields.
- [x] Excessively long fields and oversized requests receive clear errors.

## Contact and link safety

- [x] Common domain inputs are safely normalized to HTTPS.
- [x] Unsafe schemes, credentials in URLs, and malformed public hosts are rejected.
- [x] Malformed, whitespace-containing, and incomplete email addresses are rejected.
- [x] Optional agency email may be blank but must be valid when supplied.

## Failure recovery and transport

- [x] Malformed JSON receives a stable 400 response.
- [x] Non-object JSON receives a stable 400 response.
- [x] Empty and incomplete payloads do not persist guest records.
- [x] Confirmation-email failures do not lose a successfully stored application.
- [x] Browser submission is disabled while a request is in progress.
- [x] Specific validation feedback is preserved instead of being replaced by a generic error.
- [x] Draft writes are debounced and drafts remain local to the same browser/device.

## Editorial fairness and outputs

- [x] Following Mirror Talk does not improve editorial or distribution scoring.
- [x] Missing public profiles do not affect editorial eligibility.
- [x] Applicant receipt PDFs use the redesigned question wording.
- [x] Marketing consent remains separate, explicit, and optional.
- [x] Faith, boundaries, and prior speaking experience remain optional context.

## Verification

- [x] HTTP workflow tests exercise the real local web server and temporary database.
- [x] Static accessibility tests cover labels, unique IDs, assets, and keyboard-ready controls.
- [x] JavaScript syntax checks pass.
- [x] Full Python and Node regression suites pass.
- [x] Ruff, compile checks, and `git diff --check` pass.
