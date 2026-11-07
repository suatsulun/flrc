# Using the public demo

This is the visitor guide to the shared, fictional school at [flrc.suatsulun.com/demo](https://flrc.suatsulun.com/demo). Read this when evaluating the application without installing it; operators should use [Public demo operations](../operations/public-demo.md).

## Sign in and privacy

Choose Google sign-in. Any verified Google account can receive a generated temporary administrator/coordinator account; no school allowlist invitation is needed. The account lives for at most 24 hours, and an individual session can expire earlier. Logging out of your last session deactivates the account and removes its identity link.

The application does not store your Google email, name, picture, or raw Google subject. It temporarily stores a keyed hash of the subject to reuse your live account. This is pseudonymous, not anonymous; see the [privacy data map](../security/privacy-data-map.md).

Do not enter real pupil/staff information, upload real signatures, or import a real roster. This is a **shared** school: other visitors can see and change its synthetic records. Downloaded files remain on your device after the demo resets.

## What to explore

The synthetic baseline contains four academic years of pupils, classes, teachers, assignments, assessment columns, grades and comments: three archived years and one active year. It covers primary/preparatory and middle-school English, plus German and French where applicable. Changes by other visitors can alter what you find.

| Area             | Things to try                                                                                                                                                                                             |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Teacher panel    | Select a year, class and subject; edit ratings or scores; save drafts; inspect grade history. An unassigned-column save asks for confirmation rather than silently granting ownership.                    |
| Phone grade grid | Open a class on a narrow screen; use the pupil cards instead of a sideways-scrolling desktop table.                                                                                                       |
| Class report     | Open a middle-school English class report sheet: a printable whole-class summary, separate from individual report cards.                                                                                  |
| Report previews  | Preview a pupil's report card and page through the class.                                                                                                                                                 |
| PDF reports      | Generate a PDF for one class or one student. Larger report sets run as background jobs on school installations; the demo refuses them (`demo_report_class_required`) and the picker disables them.        |
| Admin dashboard  | Review school-wide completion and links to work needing attention.                                                                                                                                        |
| Admin setup      | Explore teachers, assignments, pupils/classes and assessment columns (“sütun”, report column). Use synthetic values only.                                                                                 |
| Undo             | Make a reversible administration change, then use the change history to undo it. The normal window is seven days; the nightly demo reset erases changes sooner. Conflicting later edits can prevent undo. |
| Archives         | Read historical years without changing their locked records.                                                                                                                                              |

Use the panel switch in the application navigation to move between the teacher app and `/admin`. They share your login; you do not need a second Google account. Admin privileges do not make locked or archived grade data editable.

## Reset and availability

The baseline is restored nightly at **00:00 Europe/Istanbul**. Visitor accounts, sessions and edits are removed; sign in again afterwards. A delayed schedule is caught up by the application when it wakes. During a reset, data requests can briefly return unavailable.

The free API host can sleep. The first sign-in or API request after inactivity can take longer; wait for the host to wake before trying again. A daily visitor cap and operation rate limits can also temporarily block requests. This is an evaluation environment, not persistent storage.
