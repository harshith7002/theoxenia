# Publishing the first report

Status: local preparation only. No Zenodo draft, reserved DOI, published record,
external acceptance, or submission to Berkeley is implied.

## Available routes

Zenodo's official REST API supports drafts, metadata, file upload and publication.
The website can perform the same deposit. Its GitHub integration is another route
for archiving software releases; use a report deposit for the narrative and
analysis evidence, with a link to the exact software revision.

Official sources checked 18 October 2026:

- https://developers.zenodo.org/
- https://help.zenodo.org/docs/deposit/describe-records/reserve-doi/
- https://help.zenodo.org/docs/github/

## Recommended sequence

1. Review the report's author, scope, conclusions, input credits and licenses.
2. Build and verify the reproducibility bundle using the repository instructions.
3. Create an unpublished Zenodo draft through the website, or through
   `POST https://zenodo.org/api/deposit/depositions` with the prepared metadata.
4. Upload the report and bundle to the returned `links.bucket` URL using PUT;
   check every uploaded file's size and checksum against the local files.
5. Optionally reserve a DOI in the draft and add it to the final report before
   uploading that final version. A reserved DOI is not a published record.
6. Review the actual draft. Publication is a separate, owner-approved action:
   `POST /api/deposit/depositions/{id}/actions/publish`.
7. Verify the published record and DOI, then add its real URL to the website,
   citation metadata and Notion experiment. Do not display an invented DOI.

For API use, `deposit:write` permits draft preparation without publication;
`deposit:actions` permits publishing. Use a personal access token through an
Authorization Bearer header, kept in the local environment or secret store.
Never commit it, put it in a URL, print it or paste it into a report/chat.
The sandbox (`https://sandbox.zenodo.org`) uses a separate account/token and
creates test records, not production research publications.

Zenodo preserves and makes the work citable; it does not peer review or endorse
our interpretation. Berkeley's scientific contact and upstream software
contribution routes are separate from depositing an artifact. The site must
keep prepared, submitted, published and independently reviewed statuses distinct.
