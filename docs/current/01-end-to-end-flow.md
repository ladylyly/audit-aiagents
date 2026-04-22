# 01 End-to-End Flow

## Main flow

1. The user enters a root VC CID in the audit UI.
2. The frontend sends `POST /api/run` to the backend.
3. The backend starts the orchestrator for that CID.
4. The orchestrator builds the provenance graph and fetches the VC payloads from IPFS.
5. Technical verification runs first.
6. Compliance, certification, and ESG run on the same graph and VC data.

## Report handling

1. The backend writes the finished report to `data/reports/`.
2. The frontend polls the report endpoint until the result is ready.
3. Stored reports can be reopened later from the same backend.

## Follow-up questions

1. Report questions go through `POST /api/qa`.
2. The backend answers them from the stored report data.
