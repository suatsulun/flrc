# FL-ReportCard backend

The backend is one Python project with several process entry points: the FastAPI web API,
Celery workers, maintenance commands, imports, and report generation.

Application source lives in `src/flrc`. Business features live together under
`src/flrc/modules`; shared configuration and infrastructure stay outside feature modules.

School deployments are intentionally fail-closed. Read
[the security model](../../docs/SECURITY.md) before setting `ENV=school`; the API will refuse
to start until HTTPS origins, Google Workspace identity, trusted hosts, gateway isolation, and
strong secrets are configured.
