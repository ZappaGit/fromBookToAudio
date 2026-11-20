# Security Policy

## Supported versions

Only the latest commit on `main` receives security fixes.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report it privately through GitHub: go to the **Security** tab of this repository and choose **Report a vulnerability** (private vulnerability reporting).

Please include:

- a description of the issue and its impact;
- the steps or a minimal input needed to reproduce it;
- the affected file(s) and commit, if known.

The maintainer will acknowledge the report as soon as possible and keep you informed of progress. Please allow time for a fix before any public disclosure.

## Scope

fromBookToAudio runs locally and processes files you provide. Relevant reports include, for example, unsafe handling of file paths in `input/`, `work/` or `output/`, dependency vulnerabilities that affect the code, and anything that could send book content to a third party.
