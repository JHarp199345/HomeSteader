# iCloud Drive Intake

## Purpose

An iPhone or iPad can scan a document into a designated Files/iCloud Drive folder. Once iCloud Drive has synchronized that folder to the approved Mac, Homesteader can process its local copy into the currently selected intake packet.

This is a transport and capture workflow, not a Homesteader cloud service.

```text
Files app scan
    -> approved iCloud Drive intake folder
    -> local synchronized copy on the Mac
    -> user selects the active packet in Homesteader
    -> user selects Process new scans
    -> local extraction, hashing, proposal, and review
```

## Boundaries

- Homesteader binds its interface to `127.0.0.1` only.
- It does not expose the intake folder to the network.
- It does not use an iCloud API, sign in to Apple on the user’s behalf, or change iCloud account settings.
- Processing occurs only after the user chooses **Process new scans** for an explicitly selected packet.
- Original scan files remain in the intake folder. Homesteader records their raw hash to avoid processing the exact same scan twice, and preserves a second local archive copy beside its local state file for evidence review.

## Setup

1. Create an organization-approved folder in Files/iCloud Drive, such as `Homesteader Intake`.
2. Confirm the folder is available locally on the Mac.
3. Launch Homesteader with the folder path supplied to `--inbox`.
4. Scan into that folder, select the intended packet, and choose **Process new scans**. HEIC, JPEG, PNG, and TIFF phone scans are accepted alongside PDFs and plain-text fixtures.

The default project `inbox/` remains useful for fictional fixtures and local testing. A real workplace folder must be selected deliberately rather than embedded in the repository.

## Privacy and operational rule

The organization—not Homesteader—decides whether iCloud Drive, the Apple account type, device management, and any encryption options are approved for client records. Homesteader treats the chosen folder as an already-approved local source. Its own metadata, review decisions, and extracted text require the same records-policy assessment before production use.
