# Collecting applications with a Google Form

The form keeps its own record of every response in a linked Google Sheet, which you can open in Excel. A small script attached to the form also sends each response to RecruitIQ, which scores it. No Google API key is needed. The script runs inside your own Google account.

I could not test this against a live Google Form from where I built it. The server side (a signed request carrying the resume file) is tested, the script below is not, so try it with one test response first.

## 1. Server

Set `RECRUITIQ_WEBHOOK_SECRET` to a long random string and restart. The route stays switched off while it is empty.

## 2. The form

Questions, with these exact titles: `Full name`, `Email`, `Resume (PDF or Word)` (file upload, one file) and `I agree that my application may be processed with the help of software` (a single checkbox). Link the form to a Sheet from the Responses tab.

## 3. The script

In the form, open the three-dot menu, then Script editor. Paste this, set `JOB_ID` and `API`, then under Project Settings add a script property called `WEBHOOK_SECRET` with the same secret as the server. Add a trigger: function `onFormSubmit`, event source "From form", event type "On form submit".

```javascript
const API = "https://YOUR-API-HOST/webhooks/intake";
const JOB_ID = 1;

function onFormSubmit(e) {
  const secret = PropertiesService.getScriptProperties().getProperty("WEBHOOK_SECRET");
  const items = e.response.getItemResponses();
  const get = (start) => {
    for (const it of items) if (it.getItem().getTitle().indexOf(start) === 0) return it.getResponse();
    return "";
  };
  let b64 = "", fname = "resume.pdf";
  const files = get("Resume");
  if (files && files.length) {
    const f = DriveApp.getFileById(files[0]);
    b64 = Utilities.base64Encode(f.getBlob().getBytes());
    fname = f.getName();
  }
  const agreed = get("I agree");
  const payload = JSON.stringify({
    job_id: JOB_ID, name: get("Full name"), email: get("Email"),
    consent: !!(agreed && agreed.length), source: "google_form",
    resume_base64: b64, resume_filename: fname
  });
  const sig = Utilities.computeHmacSha256Signature(payload, secret)
    .map(b => ("0" + (b & 0xff).toString(16)).slice(-2)).join("");
  UrlFetchApp.fetch(API, {
    method: "post", contentType: "application/json", payload: payload,
    headers: { "X-Signature": "sha256=" + sig }, muteHttpExceptions: true
  });
}
```

## Notes

- A file upload question makes respondents sign in to Google. If that is a problem, ask for a link or paste instead and send `resume_text`.
- The same person applying twice for the same job is ignored by the server (409). A person who does not tick the consent box is rejected (422).
- Files up to 5 MB are read. Hidden text, keyword stuffing and pasted job text are handled the same way as for uploads in the dashboard.
- To get the ranked list in Excel, use "Download this list as Excel" on the Candidates page. It leaves names out unless you ask for them, and asking is logged.
